#!/bin/bash
# PreToolUse hook on Bash, cg_run, and cg_run_many: deny a gcloud call that names its project by
# number. Cloud Build check runs on GitHub link to URLs with `?project=<number>`, and agents copy
# that number into `--project`. `gcloud builds` rejects it, and other groups vary. A project ID
# works everywhere, so the deny reason gives the command that resolves the number to one.
#
# A project ID must start with a letter, so an all-digit value is always a number. This is a regex
# match over the command text, not a shell parser. It covers the `--project` flag, `gcloud config
# set project`, and the CLOUDSDK_CORE_PROJECT variable, set inline or in cg's env.

INPUT=$(cat)

case "$INPUT" in
  *gcloud*) ;;
  *) exit 0 ;;
esac

TOOL=$(printf '%s' "$INPUT" | jq -r '.tool_name // empty')

case "$TOOL" in
  Bash)
    COMMAND=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty')
    ENV_PROJECT=""
    ;;
  mcp__cg__cg_run)
    COMMAND=$(printf '%s' "$INPUT" | jq -r '(.tool_input.command // []) | join(" ")')
    ENV_PROJECT=$(printf '%s' "$INPUT" | jq -r '.tool_input.env.CLOUDSDK_CORE_PROJECT // empty')
    ;;
  mcp__cg__cg_run_many)
    COMMAND=$(printf '%s' "$INPUT" | jq -r '(.tool_input.commands // []) | map(join(" ")) | join("\n")')
    ENV_PROJECT=$(printf '%s' "$INPUT" | jq -r '.tool_input.env.CLOUDSDK_CORE_PROJECT // empty')
    ;;
  *)
    exit 0
    ;;
esac

if ! printf '%s' "$COMMAND" | grep -qE '(^|[^[:alnum:]_-])gcloud([^[:alnum:]_-]|$)'; then
  exit 0
fi

Q="[\"']?"
END="${Q}([[:space:];&|)]|$)"
FLAG="--project(=|[[:space:]]+)${Q}[0-9]+${END}"
CONFIG="config[[:space:]]+set[[:space:]]+(core/)?project[[:space:]]+${Q}[0-9]+${END}"
VARIABLE="CLOUDSDK_CORE_PROJECT=${Q}[0-9]+${END}"

NUMBER=$(printf '%s' "$COMMAND" | grep -oE -e "$FLAG|$CONFIG|$VARIABLE" | head -n 1 | grep -oE '[0-9]+' | tail -n 1)

if [[ -z "$NUMBER" && "$ENV_PROJECT" =~ ^[0-9]+$ ]]; then
  NUMBER=$ENV_PROJECT
fi

if [[ -n "$NUMBER" ]]; then
  REASON="$NUMBER is a GCP project number, not a project ID. gcloud builds and some other command groups reject a number. Resolve it with: gcloud projects describe $NUMBER --format='value(projectId)'. Then pass the ID. A Cloud Build URL's ?project= value is always a number."
  jq -n --arg reason "$REASON" \
    '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: $reason}}'
fi

exit 0
