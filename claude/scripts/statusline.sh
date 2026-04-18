#!/bin/bash
#
# Claude Code statusline
# https://cdn.discordapp.com/attachments/688614514505285632/688615423012634664/unknown.sh
#
# Cache files (stored in ${TMPDIR:-/tmp}/claude/):
#
#   statusline-usage-cache.json         Paid-account OAuth usage data (5hr/7day/extra quotas)
#                                       TTL: 120s
#
#   statusline-git-<md5>.txt            Git branch/status per working directory
#                                       TTL: 5s. Key is MD5 of the cwd path.
#
#   bedrock-profile-<id>.txt            Bedrock inference profile → display name
#                                       TTL: 1 hour. Used by resolve_bedrock_arn().
#
#   bedrock-model-<id>.txt              Bedrock inference profile → foundation model ID
#                                       TTL: 1 hour. Used for price table lookup.
#
#   bedrock-usage-<id>.json             Composite Bedrock usage: tokens + cost for
#                                       today / 2-day / 7-day windows.
#                                       TTL: 5 min. Refreshed in background after expiry.
#
#   bedrock-usage-<id>.lock             Transient lock to prevent concurrent background
#                                       refreshes. Auto-removed after fetch completes;
#                                       stale locks (>60s) are force-removed.
#

# --- Input Validation ---

input=$(cat)
if ! echo "$input" | jq -e . >/dev/null 2>&1; then
    echo "⚠ invalid input"
    exit 0
fi

# --- Constants ---

# ANSI color codes (foreground only)
RESET=$'\033[0m'
FG_GREEN=$'\033[32m'
FG_YELLOW=$'\033[33m'
FG_BLUE=$'\033[34m'
FG_CYAN=$'\033[36m'
FG_RED=$'\033[31m'
DIM=$'\033[2m'
BOLD=$'\033[1m'
BLINK=$'\033[5m'

# Separator between segments
SEP="${DIM}│${RESET}"

# Prevent index.lock contention with Claude Code's own git operations
# (see anthropics/claude-code#11005)
export GIT_OPTIONAL_LOCKS=0

# Cache settings
cache_dir="${TMPDIR:-/tmp}/claude"
cache_file="${cache_dir}/statusline-usage-cache.json"
cache_max_age=120
git_cache_max_age=5
bedrock_cache_max_age=300

# Bedrock pricing: $/1M tokens (input output cache_read cache_write_5m)
# Source: AWS Bedrock Global Cross-region Inference, US West (Oregon)
# Override input/output with BEDROCK_INPUT_PRICE_PER_MTOK / BEDROCK_OUTPUT_PRICE_PER_MTOK env vars
declare -A BEDROCK_PRICES=(
    # Opus family
    ["anthropic.claude-opus-4-7-v1"]="5.00 25.00 0.50 6.25"
    ["anthropic.claude-opus-4-6-v1"]="5.00 25.00 0.50 6.25"
    ["anthropic.claude-opus-4-5-v1"]="5.00 25.00 0.50 6.25"
    # Sonnet 4.6
    ["anthropic.claude-sonnet-4-6-v1"]="3.00 15.00 0.30 3.75"
    ["anthropic.claude-sonnet-4-6-long-context-v1"]="3.00 15.00 0.30 3.75"
    # Sonnet 4.5 (long-context priced higher)
    ["anthropic.claude-sonnet-4-5-v1"]="3.00 15.00 0.30 3.75"
    ["anthropic.claude-sonnet-4-5-long-context-v1"]="6.00 22.50 0.60 7.50"
    # Sonnet 4 (long-context priced higher)
    ["anthropic.claude-sonnet-4-v1"]="3.00 15.00 0.30 3.75"
    ["anthropic.claude-sonnet-4-long-context-v1"]="6.00 22.50 0.60 7.50"
    # Haiku 4.5
    ["anthropic.claude-haiku-4-5-v1"]="1.00 5.00 0.10 1.25"
)

# --- Helper Functions ---

get_oauth_token() {
    if [ -n "$CLAUDE_CODE_OAUTH_TOKEN" ]; then
        echo "$CLAUDE_CODE_OAUTH_TOKEN"
        return 0
    fi

    if command -v security >/dev/null 2>&1; then
        local blob
        blob=$(security find-generic-password -s "Claude Code-credentials" -w 2>/dev/null)
        if [ -n "$blob" ]; then
            local token
            token=$(echo "$blob" | jq -r '.claudeAiOauth.accessToken // empty' 2>/dev/null)
            if [ -n "$token" ] && [ "$token" != "null" ]; then
                echo "$token"
                return 0
            fi
        fi
    fi

    echo ""
}

iso_to_epoch() {
    local iso_str="$1"

    # Try GNU date first
    local epoch
    epoch=$(date -d "${iso_str}" +%s 2>/dev/null)
    if [ -n "$epoch" ]; then
        echo "$epoch"
        return 0
    fi

    # macOS date fallback
    local stripped="${iso_str%%.*}"
    stripped="${stripped%%Z}"
    stripped="${stripped%%+*}"
    stripped="${stripped%%-[0-9][0-9]:[0-9][0-9]}"

    if [[ "$iso_str" == *"Z"* ]] || [[ "$iso_str" == *"+00:00"* ]] || [[ "$iso_str" == *"-00:00"* ]]; then
        epoch=$(env TZ=UTC date -j -f "%Y-%m-%dT%H:%M:%S" "$stripped" +%s 2>/dev/null)
    else
        epoch=$(date -j -f "%Y-%m-%dT%H:%M:%S" "$stripped" +%s 2>/dev/null)
    fi

    if [ -n "$epoch" ]; then
        echo "$epoch"
        return 0
    fi

    return 1
}

format_reset_time() {
    local iso_str="$1"
    local style="$2"
    [ -z "$iso_str" ] || [ "$iso_str" = "null" ] && return

    local epoch
    epoch=$(iso_to_epoch "$iso_str")
    [ -z "$epoch" ] && return

    local result=""
    case "$style" in
        time)
            result=$(date -j -r "$epoch" +"%H:%M" 2>/dev/null)
            [ -z "$result" ] && result=$(date -d "@$epoch" +"%H:%M" 2>/dev/null)
            ;;
        date)
            result=$(date -j -r "$epoch" +"%b-%d" 2>/dev/null | tr '[:upper:]' '[:lower:]')
            [ -z "$result" ] && result=$(date -d "@$epoch" +"%b-%d" 2>/dev/null | tr '[:upper:]' '[:lower:]')
            ;;
    esac
    printf "%s" "$result"
}

resolve_bedrock_arn() {
    local arn="$1"

    # Extract region and resource type from the ARN
    # Format: arn:aws:bedrock:<region>:<account>:<resource-type>/<resource-id>
    local region resource_type resource_id
    region=$(echo "$arn" | cut -d: -f4)
    resource_type=$(echo "$arn" | cut -d: -f6 | cut -d/ -f1)
    resource_id=$(echo "$arn" | cut -d/ -f2)

    # For foundation-model ARNs, the resource ID is already a readable model name
    if [ "$resource_type" = "foundation-model" ]; then
        echo "$resource_id"
        return 0
    fi

    # For inference profiles, try to resolve via AWS CLI with caching
    if [ "$resource_type" = "application-inference-profile" ] || [ "$resource_type" = "inference-profile" ]; then
        local profile_cache="${cache_dir}/bedrock-profile-${resource_id}.txt"

        # Check cache first (cache for 1 hour)
        if [ -f "$profile_cache" ]; then
            local pc_mtime pc_age
            pc_mtime=$(stat -c %Y "$profile_cache" 2>/dev/null || stat -f %m "$profile_cache" 2>/dev/null)
            pc_age=$(( $(date +%s) - pc_mtime ))
            if [ "$pc_age" -lt 3600 ]; then
                cat "$profile_cache"
                return 0
            fi
        fi

        # Try AWS CLI
        if command -v aws >/dev/null 2>&1; then
            local profile_name
            profile_name=$(aws bedrock get-inference-profile \
                --inference-profile-identifier "$arn" \
                --region "$region" \
                --query 'inferenceProfileName' \
                --output text 2>/dev/null)
            if [ -n "$profile_name" ] && [ "$profile_name" != "None" ]; then
                echo "$profile_name" > "$profile_cache"
                echo "$profile_name"
                return 0
            fi
        fi

        # Fallback: short profile ID
        echo "bedrock:${resource_id:0:12}"
        return 0
    fi

    # Unknown resource type: just show the tail
    echo "bedrock:${resource_id}"
}

usage_bar_color() {
    local pct=$1
    if [ "$pct" -gt 95 ]; then
        printf "%s" "$FG_RED"
    elif [ "$pct" -gt 80 ]; then
        printf "%s" "$FG_YELLOW"
    else
        printf "%s" "$FG_GREEN"
    fi
}

build_usage_bar() {
    local pct=$1
    local bar_width=5
    [ "$pct" -lt 0 ] 2>/dev/null && pct=0
    [ "$pct" -gt 100 ] 2>/dev/null && pct=100

    local filled=$(( pct * bar_width / 100 ))
    local empty=$(( bar_width - filled ))
    local bar_color
    bar_color=$(usage_bar_color "$pct")

    local filled_str="" empty_str=""
    for ((i=0; i<filled; i++)); do filled_str+="█"; done
    for ((i=0; i<empty; i++)); do empty_str+="░"; done

    printf "%s" "${bar_color}${filled_str}${RESET}${DIM}${empty_str}${RESET}"
}

format_tokens() {
    local count="$1"
    [ -z "$count" ] || [ "$count" = "null" ] && { echo "0"; return; }
    # Truncate any decimal (CloudWatch can return floats)
    count=${count%%.*}
    if [ "$count" -ge 1000000000 ] 2>/dev/null; then
        awk "BEGIN {printf \"%.1fB\", $count/1000000000}"
    elif [ "$count" -ge 1000000 ] 2>/dev/null; then
        awk "BEGIN {printf \"%.1fM\", $count/1000000}"
    elif [ "$count" -ge 1000 ] 2>/dev/null; then
        awk "BEGIN {printf \"%.1fK\", $count/1000}"
    else
        echo "$count"
    fi
}

get_date_offset() {
    local days="$1"
    if [ "$days" -ge 0 ] 2>/dev/null; then
        date -v+${days}d +%Y-%m-%d 2>/dev/null || date -d "+${days} days" +%Y-%m-%d 2>/dev/null
    else
        local abs=$(( -days ))
        date -v-${abs}d +%Y-%m-%d 2>/dev/null || date -d "${abs} days ago" +%Y-%m-%d 2>/dev/null
    fi
}

get_bedrock_foundation_model() {
    local arn="$1"
    local region resource_type resource_id
    region=$(echo "$arn" | cut -d: -f4)
    resource_type=$(echo "$arn" | cut -d: -f6 | cut -d/ -f1)
    resource_id=$(echo "$arn" | cut -d/ -f2)

    # For foundation-model ARNs, the resource ID is already the model name
    if [ "$resource_type" = "foundation-model" ]; then
        echo "$resource_id"
        return 0
    fi

    # For inference profiles, resolve to the underlying foundation model
    local model_cache="${cache_dir}/bedrock-model-${resource_id}.txt"
    if [ -f "$model_cache" ]; then
        local mc_mtime mc_age
        mc_mtime=$(stat -c %Y "$model_cache" 2>/dev/null || stat -f %m "$model_cache" 2>/dev/null)
        mc_age=$(( $(date +%s) - mc_mtime ))
        if [ "$mc_age" -lt 3600 ]; then
            cat "$model_cache"
            return 0
        fi
    fi

    if command -v aws >/dev/null 2>&1; then
        local foundation_model
        foundation_model=$(aws bedrock get-inference-profile \
            --inference-profile-identifier "$arn" \
            --region "$region" \
            --query 'models[0].modelArn' \
            --output text 2>/dev/null)
        if [ -n "$foundation_model" ] && [ "$foundation_model" != "None" ]; then
            # Extract model ID from foundation model ARN
            local fm_id
            fm_id=$(echo "$foundation_model" | cut -d/ -f2)
            if [ -n "$fm_id" ]; then
                echo "$fm_id" > "$model_cache"
                echo "$fm_id"
                return 0
            fi
        fi
    fi

    echo ""
}

get_bedrock_prices() {
    local foundation_model="$1"

    # Env var overrides take priority
    if [ -n "$BEDROCK_INPUT_PRICE_PER_MTOK" ] && [ -n "$BEDROCK_OUTPUT_PRICE_PER_MTOK" ]; then
        echo "$BEDROCK_INPUT_PRICE_PER_MTOK $BEDROCK_OUTPUT_PRICE_PER_MTOK"
        return 0
    fi

    # Look up in price table
    if [ -n "$foundation_model" ] && [ -n "${BEDROCK_PRICES[$foundation_model]+x}" ]; then
        echo "${BEDROCK_PRICES[$foundation_model]}"
        return 0
    fi

    echo ""
}

fetch_bedrock_usage_bg() {
    local model_id="$1"
    local region="$2"
    local foundation_model="$3"
    local composite_cache="${cache_dir}/bedrock-usage-${model_id}.json"
    local lock_file="${cache_dir}/bedrock-usage-${model_id}.lock"

    local today tomorrow yesterday seven_days_ago
    today=$(get_date_offset 0)
    tomorrow=$(get_date_offset 1)
    yesterday=$(get_date_offset -1)
    seven_days_ago=$(get_date_offset -6)

    # Fetch 7 days of token data in a single API call
    local cw_response
    cw_response=$(aws cloudwatch get-metric-data \
        --region "$region" \
        --start-time "${seven_days_ago}T00:00:00Z" \
        --end-time "${tomorrow}T00:00:00Z" \
        --metric-data-queries "[
            {
                \"Id\": \"input_tokens\",
                \"MetricStat\": {
                    \"Metric\": {
                        \"Namespace\": \"AWS/Bedrock\",
                        \"MetricName\": \"InputTokenCount\",
                        \"Dimensions\": [{\"Name\": \"ModelId\", \"Value\": \"${model_id}\"}]
                    },
                    \"Period\": 86400,
                    \"Stat\": \"Sum\"
                }
            },
            {
                \"Id\": \"output_tokens\",
                \"MetricStat\": {
                    \"Metric\": {
                        \"Namespace\": \"AWS/Bedrock\",
                        \"MetricName\": \"OutputTokenCount\",
                        \"Dimensions\": [{\"Name\": \"ModelId\", \"Value\": \"${model_id}\"}]
                    },
                    \"Period\": 86400,
                    \"Stat\": \"Sum\"
                }
            },
            {
                \"Id\": \"cache_read_tokens\",
                \"MetricStat\": {
                    \"Metric\": {
                        \"Namespace\": \"AWS/Bedrock\",
                        \"MetricName\": \"CacheReadInputTokenCount\",
                        \"Dimensions\": [{\"Name\": \"ModelId\", \"Value\": \"${model_id}\"}]
                    },
                    \"Period\": 86400,
                    \"Stat\": \"Sum\"
                }
            },
            {
                \"Id\": \"cache_write_tokens\",
                \"MetricStat\": {
                    \"Metric\": {
                        \"Namespace\": \"AWS/Bedrock\",
                        \"MetricName\": \"CacheWriteInputTokenCount\",
                        \"Dimensions\": [{\"Name\": \"ModelId\", \"Value\": \"${model_id}\"}]
                    },
                    \"Period\": 86400,
                    \"Stat\": \"Sum\"
                }
            }
        ]" \
        --output json 2>/dev/null)

    if [ -z "$cw_response" ]; then
        rm -f "$lock_file"
        return 1
    fi

    # Get prices for cost calculation
    local prices input_price output_price cache_read_price cache_write_price
    prices=$(get_bedrock_prices "$foundation_model")
    if [ -n "$prices" ]; then
        input_price=$(echo "$prices" | awk '{print $1}')
        output_price=$(echo "$prices" | awk '{print $2}')
        cache_read_price=$(echo "$prices" | awk '{print $3}')
        cache_write_price=$(echo "$prices" | awk '{print $4}')
    fi

    # Assemble composite JSON: sum tokens per window, calculate costs
    local result
    result=$(echo "$cw_response" | jq --arg today "$today" --arg yesterday "$yesterday" \
        --arg week_start "$seven_days_ago" \
        --arg input_price "${input_price:-}" --arg output_price "${output_price:-}" \
        --arg cache_read_price "${cache_read_price:-}" --arg cache_write_price "${cache_write_price:-}" '
        # Extract token arrays
        (.MetricDataResults // []) as $results |
        ($results | map(select(.Id == "input_tokens")) | .[0] // {Timestamps:[], Values:[]}) as $in |
        ($results | map(select(.Id == "output_tokens")) | .[0] // {Timestamps:[], Values:[]}) as $out |
        ($results | map(select(.Id == "cache_read_tokens")) | .[0] // {Timestamps:[], Values:[]}) as $cr |
        ($results | map(select(.Id == "cache_write_tokens")) | .[0] // {Timestamps:[], Values:[]}) as $cw |

        # Build a date->value map for each metric
        (reduce range($in.Timestamps | length) as $i ({}; . + {($in.Timestamps[$i] | split("T")[0]): $in.Values[$i]})) as $in_map |
        (reduce range($out.Timestamps | length) as $i ({}; . + {($out.Timestamps[$i] | split("T")[0]): $out.Values[$i]})) as $out_map |
        (reduce range($cr.Timestamps | length) as $i ({}; . + {($cr.Timestamps[$i] | split("T")[0]): $cr.Values[$i]})) as $cr_map |
        (reduce range($cw.Timestamps | length) as $i ({}; . + {($cw.Timestamps[$i] | split("T")[0]): $cw.Values[$i]})) as $cw_map |

        # Sum tokens for each window
        def sum_range(start_date; end_date; map):
            [map | to_entries[] | select(.key >= start_date and .key <= end_date) | .value] | add // 0;

        (sum_range($today; $today; $in_map)) as $today_in |
        (sum_range($today; $today; $out_map)) as $today_out |
        (sum_range($today; $today; $cr_map)) as $today_cr |
        (sum_range($today; $today; $cw_map)) as $today_cw |
        (sum_range($yesterday; $today; $in_map)) as $two_in |
        (sum_range($yesterday; $today; $out_map)) as $two_out |
        (sum_range($yesterday; $today; $cr_map)) as $two_cr |
        (sum_range($yesterday; $today; $cw_map)) as $two_cw |
        (sum_range($week_start; $today; $in_map)) as $seven_in |
        (sum_range($week_start; $today; $out_map)) as $seven_out |
        (sum_range($week_start; $today; $cr_map)) as $seven_cr |
        (sum_range($week_start; $today; $cw_map)) as $seven_cw |

        # Calculate costs if prices available
        def calc_cost(in_tok; out_tok; cr_tok; cw_tok):
            if $input_price != "" and $output_price != "" then
                ( in_tok * ($input_price | tonumber)
                + out_tok * ($output_price | tonumber)
                + (if $cache_read_price != "" then cr_tok * ($cache_read_price | tonumber) else 0 end)
                + (if $cache_write_price != "" then cw_tok * ($cache_write_price | tonumber) else 0 end)
                ) / 1000000
                | . * 100 | round | . / 100 | tostring
            else null end;

        {
            today: {
                input_tokens: ($today_in | floor),
                output_tokens: ($today_out | floor),
                cache_read_tokens: ($today_cr | floor),
                cache_write_tokens: ($today_cw | floor),
                cost: calc_cost($today_in; $today_out; $today_cr; $today_cw)
            },
            two_day: {
                input_tokens: ($two_in | floor),
                output_tokens: ($two_out | floor),
                cache_read_tokens: ($two_cr | floor),
                cache_write_tokens: ($two_cw | floor),
                cost: calc_cost($two_in; $two_out; $two_cr; $two_cw)
            },
            seven_day: {
                input_tokens: ($seven_in | floor),
                output_tokens: ($seven_out | floor),
                cache_read_tokens: ($seven_cr | floor),
                cache_write_tokens: ($seven_cw | floor),
                cost: calc_cost($seven_in; $seven_out; $seven_cr; $seven_cw)
            },
            prices: (if $input_price != "" then {
                input: $input_price,
                output: $output_price,
                cache_read: (if $cache_read_price != "" then $cache_read_price else null end),
                cache_write: (if $cache_write_price != "" then $cache_write_price else null end)
            } else null end),
            fetched_at: (now | todate)
        }
    ' 2>/dev/null)

    if [ -n "$result" ] && echo "$result" | jq -e '.today' >/dev/null 2>&1; then
        echo "$result" > "$composite_cache"
    fi

    rm -f "$lock_file"
}

get_bedrock_usage() {
    local arn="$1"
    local region model_id
    region=$(echo "$arn" | cut -d: -f4)
    model_id=$(echo "$arn" | cut -d/ -f2)

    local composite_cache="${cache_dir}/bedrock-usage-${model_id}.json"
    local lock_file="${cache_dir}/bedrock-usage-${model_id}.lock"

    # Check composite cache
    if [ -f "$composite_cache" ]; then
        local cc_mtime cc_age
        cc_mtime=$(stat -c %Y "$composite_cache" 2>/dev/null || stat -f %m "$composite_cache" 2>/dev/null)
        cc_age=$(( $(date +%s) - cc_mtime ))
        if [ "$cc_age" -lt "$bedrock_cache_max_age" ]; then
            cat "$composite_cache"
            return 0
        fi

        # Cache is stale — return stale data and refresh in background
        if ! command -v aws >/dev/null 2>&1; then
            cat "$composite_cache"
            return 0
        fi

        # Don't launch another background refresh if one is already running
        if [ -f "$lock_file" ]; then
            local lk_mtime lk_age
            lk_mtime=$(stat -c %Y "$lock_file" 2>/dev/null || stat -f %m "$lock_file" 2>/dev/null)
            lk_age=$(( $(date +%s) - lk_mtime ))
            # Stale lock (>60s) — remove it
            if [ "$lk_age" -gt 60 ]; then
                rm -f "$lock_file"
            else
                cat "$composite_cache"
                return 0
            fi
        fi

        # Resolve foundation model for pricing
        local foundation_model
        foundation_model=$(get_bedrock_foundation_model "$arn")

        # Launch background refresh
        touch "$lock_file"
        fetch_bedrock_usage_bg "$model_id" "$region" "$foundation_model" &
        disown 2>/dev/null

        cat "$composite_cache"
        return 0
    fi

    # No cache at all — first run, must block
    if ! command -v aws >/dev/null 2>&1; then
        return 1
    fi

    local foundation_model
    foundation_model=$(get_bedrock_foundation_model "$arn")

    touch "$lock_file"
    fetch_bedrock_usage_bg "$model_id" "$region" "$foundation_model"

    if [ -f "$composite_cache" ]; then
        cat "$composite_cache"
        return 0
    fi

    return 1
}

# --- Data Extraction ---

mkdir -p "$cache_dir" 2>/dev/null

cwd=$(echo "$input" | jq -r '.workspace.current_dir // empty' 2>/dev/null)
dir_name=$(basename "$cwd" 2>/dev/null || echo "?")

# Extract model - prefer display_name, fall back to id/name/string
model=$(echo "$input" | jq -r '
  if .model | type == "object" then .model.display_name // .model.id // .model.name // "claude"
  elif .model | type == "string" then .model
  else "claude"
  end
' 2>/dev/null)
{ [ -z "$model" ] || [ "$model" = "null" ]; } && model="claude"
# Preserve raw model string for Bedrock usage detection
model_raw="$model"
is_bedrock=false
if [[ "$model" == arn:aws:bedrock:* ]]; then
    is_bedrock=true
    model=$(resolve_bedrock_arn "$model")
fi
# Clean up model name:
# remove claude- prefix, trailing date suffix (8+ digits), and parenthesized context size
model=$(echo "$model" | sed 's/^claude-//' | sed 's/-[0-9]\{8,\}$//' | sed 's/ *([^)]*context[^)]*)$//')

# --- Git Segment ---

git_segment=""
git_cache_key=$(printf '%s' "$cwd" | md5 -q 2>/dev/null || printf '%s' "$cwd" | md5sum 2>/dev/null | cut -d' ' -f1)
git_cache_file="${cache_dir}/statusline-git-${git_cache_key}.txt"

if [ -f "$git_cache_file" ]; then
    gc_mtime=$(stat -c %Y "$git_cache_file" 2>/dev/null || stat -f %m "$git_cache_file" 2>/dev/null)
    gc_age=$(( $(date +%s) - gc_mtime ))
    if [ "$gc_age" -lt "$git_cache_max_age" ]; then
        git_segment=$(cat "$git_cache_file")
    fi
fi

if [ -z "$git_segment" ]; then
    branch_color=$FG_CYAN
    if git -C "$cwd" rev-parse --git-dir > /dev/null 2>&1; then
        branch=$(git -C "$cwd" branch --show-current 2>/dev/null)
        [ -z "$branch" ] && branch=$(git -C "$cwd" rev-parse --short HEAD 2>/dev/null)

        # Get status counts
        status=$(git -C "$cwd" status --porcelain 2>/dev/null)
        if [ -n "$status" ]; then
            staged=$(echo "$status" | grep -c '^[MADRC]')
            modified=$(echo "$status" | grep -c '^.[MD]')
        else
            staged=0
            modified=0
        fi

        # Ahead/behind
        ahead=$(git -C "$cwd" rev-list --count @{u}..HEAD 2>/dev/null || echo 0)
        behind=$(git -C "$cwd" rev-list --count HEAD..@{u} 2>/dev/null || echo 0)
        ahead=${ahead:-0}
        behind=${behind:-0}

        # Build compact git status (starship style)
        git_status=""
        [ "$ahead" -gt 0 ] && git_status+=" ⇡$ahead"
        [ "$behind" -gt 0 ] && git_status+=" ⇣$behind"
        [ "$staged" -gt 0 ] && git_status+=" +$staged"
        [ "$modified" -gt 0 ] && git_status+=" !$modified"

        if [ -n "$git_status" ]; then
            branch_color=$FG_YELLOW
            git_segment=" ${SEP} ${branch_color}${BOLD} $branch${RESET}${FG_YELLOW}${git_status}${RESET}"
        else
            git_segment=" ${SEP} ${branch_color}${BOLD} $branch${RESET}"
        fi
    fi

    [ -n "$git_segment" ] && printf '%s' "$git_segment" > "$git_cache_file"
fi

# --- Context Bar Segment ---

context_segment=""
pct=$(echo "$input" | jq '.context_window.used_percentage // empty' 2>/dev/null)

# Recalculate pct relative to auto-compact window if configured
cap_segment=""
if [ -n "$CLAUDE_CODE_AUTO_COMPACT_WINDOW" ] && [ "$CLAUDE_CODE_AUTO_COMPACT_WINDOW" -gt 0 ] 2>/dev/null; then
    ctx_size=$(echo "$input" | jq '.context_window.context_window_size // empty' 2>/dev/null)
    if [ -n "$ctx_size" ] && [ "$ctx_size" -gt 0 ] 2>/dev/null && [ -n "$pct" ] && [ "$pct" != "null" ]; then
        pct=$(( pct * ctx_size / CLAUDE_CODE_AUTO_COMPACT_WINDOW ))
    fi
    cap_k=$(( CLAUDE_CODE_AUTO_COMPACT_WINDOW / 1000 ))
    cap_segment=" ${DIM}@${cap_k}k${RESET}"
fi

if [ -n "$pct" ] && [ "$pct" != "null" ] && [ "$pct" -ge 0 ] 2>/dev/null; then
    # Build progress bar (10 chars wide)
    bar_width=5
    filled=$((pct * bar_width / 100))
    [ "$filled" -gt "$bar_width" ] && filled=$bar_width
    empty=$((bar_width - filled))

    # Colors for filled portion based on level
    if [ "$pct" -gt 95 ]; then
        fill_color=$FG_RED
        bar_blink=$BLINK
    elif [ "$pct" -gt 85 ]; then
        fill_color=$FG_RED
        bar_blink=""
    elif [ "$pct" -gt 70 ]; then
        fill_color=$FG_YELLOW
        bar_blink=""
    else
        fill_color=$FG_GREEN
        bar_blink=""
    fi

    # Build the bar string
    filled_bar=""
    empty_bar=""
    for ((i=0; i<filled; i++)); do filled_bar+="█"; done
    for ((i=0; i<empty; i++)); do empty_bar+="░"; done

    context_segment=" ${SEP} ${bar_blink}${fill_color}${filled_bar}${RESET}${DIM}${empty_bar}${RESET} ${pct}%"
fi

# Fallback if no context data
if [ -z "$context_segment" ]; then
    context_segment=" ${SEP} ${DIM}░░░░░░░░░░ --%${RESET}"
fi

# Model color based on context window pressure
model_color=$FG_GREEN
if [ -n "$pct" ] && [ "$pct" != "null" ] && [ "$pct" -ge 0 ] 2>/dev/null; then
    if [ "$pct" -gt 95 ]; then
        model_color="${BLINK}${FG_RED}"
    elif [ "$pct" -gt 85 ]; then
        model_color=$FG_RED
    elif [ "$pct" -gt 70 ]; then
        model_color=$FG_YELLOW
    fi
fi

# --- Usage Data Fetch + Cache ---

bedrock_usage_data=""
usage_data=""

if $is_bedrock; then
    bedrock_usage_data=$(get_bedrock_usage "$model_raw")
else
    needs_refresh=true
    if [ -f "$cache_file" ]; then
        cache_mtime=$(stat -c %Y "$cache_file" 2>/dev/null || stat -f %m "$cache_file" 2>/dev/null)
        now=$(date +%s)
        cache_age=$(( now - cache_mtime ))
        if [ "$cache_age" -lt "$cache_max_age" ]; then
            needs_refresh=false
            usage_data=$(cat "$cache_file" 2>/dev/null)
        fi
    fi

    if $needs_refresh; then
        token=$(get_oauth_token)
        if [ -n "$token" ] && [ "$token" != "null" ]; then
            response=$(curl -s --max-time 5 \
                -H "Accept: application/json" \
                -H "Content-Type: application/json" \
                -H "Authorization: Bearer $token" \
                -H "anthropic-beta: oauth-2025-04-20" \
                -H "User-Agent: claude-code/2.1.34" \
                "https://api.anthropic.com/api/oauth/usage" 2>/dev/null)
            if [ -n "$response" ] && echo "$response" | jq -e '.five_hour' >/dev/null 2>&1; then
                usage_data="$response"
                echo "$response" > "$cache_file"
            fi
        fi
        if [ -z "$usage_data" ] && [ -f "$cache_file" ]; then
            usage_data=$(cat "$cache_file" 2>/dev/null)
        fi
    fi
fi

# --- Usage Segment Assembly ---

usage_segments=""
if $is_bedrock && [ -n "$bedrock_usage_data" ] && echo "$bedrock_usage_data" | jq -e '.today' >/dev/null 2>&1; then
    today_in=$(echo "$bedrock_usage_data" | jq -r '.today.input_tokens // 0')
    today_out=$(echo "$bedrock_usage_data" | jq -r '.today.output_tokens // 0')
    today_total=$(( today_in + today_out ))
    today_cost=$(echo "$bedrock_usage_data" | jq -r '.today.cost // empty')
    today_fmt=$(format_tokens "$today_total")

    two_in=$(echo "$bedrock_usage_data" | jq -r '.two_day.input_tokens // 0')
    two_out=$(echo "$bedrock_usage_data" | jq -r '.two_day.output_tokens // 0')
    two_total=$(( two_in + two_out ))
    two_cost=$(echo "$bedrock_usage_data" | jq -r '.two_day.cost // empty')
    two_fmt=$(format_tokens "$two_total")

    seven_in=$(echo "$bedrock_usage_data" | jq -r '.seven_day.input_tokens // 0')
    seven_out=$(echo "$bedrock_usage_data" | jq -r '.seven_day.output_tokens // 0')
    seven_total=$(( seven_in + seven_out ))
    seven_cost=$(echo "$bedrock_usage_data" | jq -r '.seven_day.cost // empty')
    seven_fmt=$(format_tokens "$seven_total")

    # Build segments: "1d 31.1K $1.84" or "1d 31.1K" if no prices
    for label_day in "1d:$today_fmt:$today_cost" "2d:$two_fmt:$two_cost" "7d:$seven_fmt:$seven_cost"; do
        lbl="${label_day%%:*}"
        rest="${label_day#*:}"
        tok="${rest%%:*}"
        cost="${rest#*:}"
        seg=" ${SEP} ${DIM}${lbl}${RESET} ${FG_CYAN}${tok}${RESET}"
        if [ -n "$cost" ] && [ "$cost" != "null" ]; then
            seg+=" ${DIM}\$${cost}${RESET}"
        fi
        usage_segments+="$seg"
    done
elif [ -n "$usage_data" ] && echo "$usage_data" | jq -e . >/dev/null 2>&1; then
    five_pct=$(echo "$usage_data" | jq -r '.five_hour.utilization // 0' | awk '{printf "%.0f", $1}')
    five_reset_iso=$(echo "$usage_data" | jq -r '.five_hour.resets_at // empty')
    five_reset=$(format_reset_time "$five_reset_iso" "time")
    five_bar=$(build_usage_bar "$five_pct")
    five_color=$(usage_bar_color "$five_pct")

    seven_pct=$(echo "$usage_data" | jq -r '.seven_day.utilization // 0' | awk '{printf "%.0f", $1}')
    seven_reset_iso=$(echo "$usage_data" | jq -r '.seven_day.resets_at // empty')
    seven_reset=$(format_reset_time "$seven_reset_iso" "date")
    seven_bar=$(build_usage_bar "$seven_pct")
    seven_color=$(usage_bar_color "$seven_pct")

    usage_segments=" ${SEP} ${five_bar} ${five_color}${five_pct}%${RESET} ${DIM}${five_reset}${RESET}"
    usage_segments+=" ${SEP} ${seven_bar} ${seven_color}${seven_pct}%${RESET} ${DIM}${seven_reset}${RESET}"

    extra_enabled=$(echo "$usage_data" | jq -r '.extra_usage.is_enabled // false')
    if [ "$extra_enabled" = "true" ] && { [ "$five_pct" -ge 90 ] || [ "$seven_pct" -ge 90 ]; }; then
        extra_used_raw=$(echo "$usage_data" | jq -r '.extra_usage.used_credits // 0')
        if [ "$extra_used_raw" != "0" ] && [ "$extra_used_raw" != "0.0" ]; then
            extra_pct=$(echo "$usage_data" | jq -r '.extra_usage.utilization // 0' | awk '{printf "%.0f", $1}')
            extra_bar=$(build_usage_bar "$extra_pct")
            extra_color=$(usage_bar_color "$extra_pct")
            extra_used=$(echo "$extra_used_raw" | awk '{printf "%.2f", $1/100}')
            extra_limit=$(echo "$usage_data" | jq -r '.extra_usage.monthly_limit // 0' | awk '{printf "%.2f", $1/100}')
            usage_segments+=" ${SEP} ${extra_bar} ${extra_color}\$${extra_used}${DIM}/${RESET}\$${extra_limit}"
        fi
    fi
fi

# --- Output Assembly ---

current_datetime=$(date +"%Y-%m-%d %H:%M")

echo -n "${model_color}${BOLD}${model}${RESET}${cap_segment}"
echo -n " ${SEP} ${FG_BLUE}${BOLD} ${dir_name}${RESET}"
echo -n "$git_segment"
echo -n "$context_segment"
echo -n " ${SEP} ${DIM}${current_datetime}${RESET}"
echo -n "$usage_segments"
