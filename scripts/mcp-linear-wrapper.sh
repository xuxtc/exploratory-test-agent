#!/usr/bin/env bash
# Wrapper that boots the Linear MCP server with LINEAR_API_KEY
# read from config/dispatch-env.json.
#
# Why this exists: Claude Code does NOT expand ${VAR} references in .mcp.json
# `env` blocks against local config files, and GUI-launched Claude Code does
# not read shell rc files. So the only reliable place to inject the token is
# inside the MCP server's own startup — i.e. here, right before exec'ing npx.

set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
config_file="$script_dir/../../config/dispatch-env.json"

if [[ ! -f "$config_file" ]]; then
  echo "mcp-linear-wrapper: $config_file not found — copy from config/dispatch-env.json.example and fill in token" >&2
  exit 1
fi

key="$(jq -r '.LINEAR_API_KEY // empty' "$config_file")"
if [[ -z "$key" || "$key" == lin_api_xxx* ]]; then
  echo "mcp-linear-wrapper: LINEAR_API_KEY missing or placeholder in $config_file" >&2
  exit 1
fi

export LINEAR_API_KEY="$key"
exec npx -y mcp-remote https://mcp.linear.app/mcp
