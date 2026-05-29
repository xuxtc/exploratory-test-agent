#!/bin/bash
# PreToolUse hook — records tool call start into timing.log.
# Covers: mcp__chrome-devtools__*, mcp__linear__*, mcp__github__*
#
# Payload arrives on stdin as JSON:
#   { "tool_name": "mcp__chrome-devtools__click",
#     "tool_input": { ... },
#     "session_id": "...",
#     "cwd": "..." }
#
# Writes one JSONL line to artifacts/<run-id>/timing.log:
#   { "ts": "...", "hook": "pre", "tool": "...", "detail": "...", "session_id": "..." }
set -euo pipefail

INPUT="$(cat)"

CWD="$(printf '%s' "$INPUT" | jq -r '.cwd // empty')"
[ -z "$CWD" ] && exit 0

# Only fire inside exploratory-test-agent
case "$CWD" in
  */exploratory-test-agent|*/exploratory-test-agent/*) ;;
  *) exit 0 ;;
esac

# Find the unique active run via .active marker (same logic as log-intervention.sh)
shopt -s nullglob
markers=( "$CWD"/artifacts/*/.active )
[ ${#markers[@]} -eq 1 ] || exit 0
run_dir="$(dirname "${markers[0]}")"
timing_log="$run_dir/timing.log"

TOOL="$(printf '%s' "$INPUT" | jq -r '.tool_name // empty')"
[ -z "$TOOL" ] && exit 0

SESSION="$(printf '%s' "$INPUT" | jq -r '.session_id // empty')"
TOOL_INPUT="$(printf '%s' "$INPUT" | jq -c '.tool_input // {}')"

# Build a compact detail string from the most useful input fields per tool family
detail=""
case "$TOOL" in
  mcp__chrome-devtools__navigate_page)
    detail="$(printf '%s' "$TOOL_INPUT" | jq -r '(.url // .type // "") | @text')"
    ;;
  mcp__chrome-devtools__click)
    detail="$(printf '%s' "$TOOL_INPUT" | jq -r '(.selector // .x // "") | @text')"
    ;;
  mcp__chrome-devtools__fill|mcp__chrome-devtools__type_text)
    detail="$(printf '%s' "$TOOL_INPUT" | jq -r '(.selector // "") | @text')"
    ;;
  mcp__chrome-devtools__wait_for)
    detail="$(printf '%s' "$TOOL_INPUT" | jq -r '((.text // []) | join("|")) + " timeout=" + ((.timeout // 10000) | tostring)')"
    ;;
  mcp__chrome-devtools__take_screenshot)
    detail="$(printf '%s' "$TOOL_INPUT" | jq -r '(.name // "") | @text')"
    ;;
  mcp__chrome-devtools__evaluate_script)
    # First 80 chars of the script body
    detail="$(printf '%s' "$TOOL_INPUT" | jq -r '(.script // "") | @text' | head -c 80)"
    ;;
  mcp__linear__get_issue|mcp__linear__list_comments)
    detail="$(printf '%s' "$TOOL_INPUT" | jq -r '(.id // .issueId // "") | @text')"
    ;;
  mcp__linear__save_comment)
    detail="$(printf '%s' "$TOOL_INPUT" | jq -r '(.issueId // "") | @text')"
    ;;
  mcp__github__get_pull_request|mcp__github__get_pull_request_files)
    detail="$(printf '%s' "$TOOL_INPUT" | jq -r '("pr=" + ((.pullNumber // .pull_number // 0) | tostring))')"
    ;;
  mcp__github__get_pull_request_reviews|mcp__github__get_pull_request_comments)
    detail="$(printf '%s' "$TOOL_INPUT" | jq -r '("pr=" + ((.pullNumber // .pull_number // 0) | tostring))')"
    ;;
  *)
    detail=""
    ;;
esac

TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Also write a temp file so PostToolUse can compute elapsed
tmp_dir="${TMPDIR:-/tmp}/timing-hooks"
mkdir -p "$tmp_dir"
# Key: session + tool invocation sequence — use pid of this process as unique suffix
tmp_file="$tmp_dir/${SESSION}_${TOOL}_$$"
printf '%s' "$TS" > "$tmp_file"
# Store timing.log path so PostToolUse can find it without re-resolving
printf '\n%s' "$timing_log" >> "$tmp_file"

jq -nc \
  --arg ts "$TS" \
  --arg tool "$TOOL" \
  --arg detail "$detail" \
  --arg session "$SESSION" \
  --arg tmp "$tmp_file" \
  '{ts:$ts, hook:"pre", tool:$tool, detail:$detail, session_id:$session, _tmp:$tmp}' \
  >> "$timing_log"

exit 0
