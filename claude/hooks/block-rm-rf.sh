#!/bin/bash
# PreToolUse hook on Bash: deny `rm` when one invocation has both a recursive
# and a force flag (-rf, -fr, -Rf, -r -f, --recursive --force, ...). The reason
# looks at each operand on disk. It suggests `unlink` for a file or symlink and
# `rmdir` for an empty directory, so the agent deletes only what it means to.
#
# This is a heuristic tokenizer, not a shell parser. It splits the command on
# ; & | and newlines, then on whitespace, and ignores quoting. An `rm` word
# anywhere in a segment counts, so `sudo rm -rf` and `xargs rm -rf` are caught.
# Flags only count when they follow that `rm` in the same segment, so
# `rm a && ls -R -f` passes. A quoted "rm -rf" inside a grep pattern passes too.

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty')
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')

# Operand names can hold quotes, so let jq build the JSON.
deny() {
  jq -cn --arg reason "$1" \
    '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$reason}}'
  exit 0
}

# Print advice for one operand, based on what is on disk right now.
advise() {
  local op=$1 path=$1 n
  case $op in
    *[\*\?\[\$\`]*)
      printf ' %s is a pattern or variable. Expand it yourself and handle each match.' "$op"
      return
      ;;
  esac
  case $path in
    \~ | \~/*) path=$HOME${path#\~} ;;
    /*) ;;
    *) [[ -n "$CWD" ]] && path=$CWD/$path ;;
  esac
  if [[ -L "$path" ]]; then
    printf ' %s is a symlink. Use unlink %s.' "$op" "$op"
  elif [[ -f "$path" ]]; then
    printf ' %s is a file. Use unlink %s.' "$op" "$op"
  elif [[ -d "$path" ]]; then
    n=$(find "$path" -mindepth 1 -maxdepth 1 2>/dev/null | wc -l | tr -d ' ')
    if [[ "$n" == 0 ]]; then
      printf ' %s is an empty directory. Use rmdir %s.' "$op" "$op"
    else
      printf ' %s is a directory with %s entries. Empty it with unlink and rmdir first, or ask the user to delete it.' "$op" "$n"
    fi
  else
    printf ' %s does not exist.' "$op"
  fi
}

if [[ "$TOOL" == "Bash" ]]; then
  while IFS= read -r segment; do
    read -ra words <<<"$segment"
    in_rm=0 end_opts=0 recursive=0 force=0
    operands=()
    for w in "${words[@]}"; do
      if ((!in_rm)); then
        [[ "$w" == rm || "$w" == */rm ]] && in_rm=1
        continue
      fi
      case $w in
        *[\<\>\(\)]*) continue ;;
      esac
      if ((!end_opts)); then
        case $w in
          --) end_opts=1; continue ;;
          --recursive) recursive=1; continue ;;
          --force) force=1; continue ;;
          --*) continue ;;
          -?*)
            [[ "$w" == *[rR]* ]] && recursive=1
            [[ "$w" == *f* ]] && force=1
            continue
            ;;
        esac
      fi
      operands+=("$w")
    done

    if ((recursive && force)); then
      reason="Blocked: rm with both recursive and force flags is disabled by your safety hook."
      reason+=" Delete only what you mean to. Use unlink for one file and rmdir for one empty directory."
      for op in "${operands[@]}"; do
        reason+=$(advise "$op")
      done
      deny "$reason"
    fi
  done <<<"$(printf '%s\n' "$COMMAND" | tr ';&|' '\n')"
fi

exit 0
