#!/bin/bash
# PostToolUse hook — records tool call end + elapsed_s into timing.log.
# Covers: mcp__chrome-devtools__*, mcp__linear__*, mcp__github__*
#
# Payload arrives on stdin as JSON:
#   { "tool_name": "...",
#     "tool_input": { ... },
#     "tool_response": { ... },
#     "session_id": "...",
#     "cwd": "..." }
#
# Writes one JSONL line to artifacts/<run-id>/timing.log:
#   { "ts": "...", "hook": "post", "tool": "...", "elapsed_s": N,
#     "outcome": "ok|timeout|error", "session_id": "..." }
set -euo pipefail

INPUT="$(cat)"

CWD="$(printf '%s' "$INPUT" | jq -r '.cwd // empty')"
[ -z "$CWD" ] && exit 0

case "$CWD" in
  */exploratory-test-agent|*/exploratory-test-agent/*) ;;
  *) exit 0 ;;
esac

shopt -s nullglob
markers=( "$CWD"/artifacts/*/.active )
[ ${#markers[@]} -eq 1 ] || exit 0
run_dir="$(dirname "${markers[0]}")"
timing_log="$run_dir/timing.log"

TOOL="$(printf '%s' "$INPUT" | jq -r '.tool_name // empty')"
[ -z "$TOOL" ] && exit 0

SESSION="$(printf '%s' "$INPUT" | jq -r '.session_id // empty')"
TS_END="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
TS_END_EPOCH="$(date -u +%s)"

# Find the matching pre-hook temp file for this session+tool
# Use the most recently written one (in case of rare parallel calls)
tmp_dir="${TMPDIR:-/tmp}/timing-hooks"
tmp_file=""
elapsed_s=""
if [ -d "$tmp_dir" ]; then
  tmp_file="$(ls -t "$tmp_dir"/${SESSION}_${TOOL}_* 2>/dev/null | head -1)"
fi

if [ -n "$tmp_file" ] && [ -f "$tmp_file" ]; then
  TS_START="$(head -1 "$tmp_file")"
  TS_START_EPOCH="$(date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$TS_START" +%s 2>/dev/null \
    || date -u -d "$TS_START" +%s 2>/dev/null \
    || echo "")"
  if [ -n "$TS_START_EPOCH" ]; then
    elapsed_s=$(( TS_END_EPOCH - TS_START_EPOCH ))
  fi
  rm -f "$tmp_file"
fi

# Determine outcome from tool response
RESPONSE="$(printf '%s' "$INPUT" | jq -c '.tool_response // {}')"
outcome="ok"
if printf '%s' "$RESPONSE" | jq -e 'type == "object" and (.error != null)' > /dev/null 2>&1; then
  err_msg="$(printf '%s' "$RESPONSE" | jq -r '.error | if type=="string" then . else tostring end' | head -c 120)"
  case "$err_msg" in
    *timeout*|*Timeout*|*TIMEOUT*) outcome="timeout" ;;
    *) outcome="error" ;;
  esac
elif printf '%s' "$RESPONSE" | jq -e 'type == "string"' > /dev/null 2>&1; then
  err_msg="$(printf '%s' "$RESPONSE" | jq -r '.' | head -c 120)"
  case "$err_msg" in
    *timeout*|*Timeout*|*TIMEOUT*) outcome="timeout" ;;
    *Error*|*error*|*failed*|*Failed*) outcome="error" ;;
  esac
fi

# Build elapsed_s field (null if we couldn't compute it)
if [ -n "$elapsed_s" ]; then
  elapsed_field="\"elapsed_s\":$elapsed_s"
else
  elapsed_field="\"elapsed_s\":null"
fi

jq -nc \
  --arg ts "$TS_END" \
  --arg tool "$TOOL" \
  --arg outcome "$outcome" \
  --arg session "$SESSION" \
  --argjson elapsed "${elapsed_s:-null}" \
  '{ts:$ts, hook:"post", tool:$tool, elapsed_s:$elapsed, outcome:$outcome, session_id:$session}' \
  >> "$timing_log"

exit 0
