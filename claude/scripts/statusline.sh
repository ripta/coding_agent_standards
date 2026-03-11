#!/bin/bash
#
# Claude Code statusline
# https://cdn.discordapp.com/attachments/688614514505285632/688615423012634664/unknown.sh

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

# Usage cache settings
cache_file="${TMPDIR:-/tmp}/claude/statusline-usage-cache.json"
cache_max_age=180

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

usage_bar_color() {
    local pct=$1
    if [ "$pct" -gt 85 ]; then
        printf "%s" "$FG_RED"
    elif [ "$pct" -gt 70 ]; then
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

# --- Data Extraction ---

cwd=$(echo "$input" | jq -r '.workspace.current_dir // empty' 2>/dev/null)
dir_name=$(basename "$cwd" 2>/dev/null || echo "?")

# Extract model - could be string or object with .id field
model=$(echo "$input" | jq -r '
  if .model | type == "object" then .model.id // .model.name // "claude"
  elif .model | type == "string" then .model
  else "claude"
  end
' 2>/dev/null)
{ [ -z "$model" ] || [ "$model" = "null" ]; } && model="claude"
# Clean up model name - remove claude- prefix and date suffix, truncate
model=$(echo "$model" | sed 's/claude-//' | sed 's/-[0-9]*$//' | cut -c1-10)

# --- Git Segment ---

git_segment=""
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

# --- Context Bar Segment ---

context_segment=""
pct=$(echo "$input" | jq '.context_window.used_percentage // empty' 2>/dev/null)
if [ -n "$pct" ] && [ "$pct" != "null" ] && [ "$pct" -ge 0 ] 2>/dev/null; then
    # Build progress bar (10 chars wide)
    bar_width=10
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

# --- Usage Data Fetch + Cache ---

mkdir -p ${TMPDIR:-/tmp}/claude 2>/dev/null

needs_refresh=true
usage_data=""

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

# --- Usage Segment Assembly ---

usage_segments=""
if [ -n "$usage_data" ] && echo "$usage_data" | jq -e . >/dev/null 2>&1; then
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
    if [ "$extra_enabled" = "true" ]; then
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

echo -n "${model_color}${BOLD}${model}${RESET}"
echo -n " ${SEP} ${FG_BLUE}${BOLD} ${dir_name}${RESET}"
echo -n "$git_segment"
echo -n "$context_segment"
echo -n " ${SEP} ${DIM}${current_datetime}${RESET}"
echo -n "$usage_segments"
