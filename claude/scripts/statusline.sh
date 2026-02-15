#!/bin/bash
#
# Claude Code statusline
# https://cdn.discordapp.com/attachments/688614514505285632/688615423012634664/unknown.sh

input=$(cat)
if ! echo "$input" | jq -e . >/dev/null 2>&1; then
    echo "⚠ invalid input"
    exit 0
fi

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

# Git info
git_segment=""
model_color=$FG_GREEN
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
        model_color=$FG_YELLOW
        git_segment=" ${SEP} ${FG_CYAN}${BOLD} $branch${RESET}${FG_YELLOW}${git_status}${RESET}"
    else
        model_color=$FG_GREEN
        git_segment=" ${SEP} ${FG_CYAN}${BOLD} $branch${RESET}"
    fi
fi

# Context progress bar (uses built-in used_percentage from Claude Code 2.1.6+)
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

# Date and time
current_datetime=$(date +"%Y/%m/%d %H:%M")

# Build output: model | dir | git branch status | context bar | datetime
echo -n "${model_color}${BOLD}${model}${RESET}"
echo -n " ${SEP} ${FG_BLUE}${BOLD} ${dir_name}${RESET}"
echo -n "$git_segment"
echo -n "$context_segment"
echo -n " ${SEP} ${DIM}${current_datetime}${RESET}"
