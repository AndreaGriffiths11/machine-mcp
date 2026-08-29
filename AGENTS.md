# Agent notes for machine-mcp

You are using the human's laptop through this MCP server. stdio means you are already inside their process. Do not invent a pairing step. Do not ask them to log into GitHub, Copilot, or Cursor through these tools.

## What this is

Laptop-side tools: status, run, record_terminal, write_file, read_file. Workspace root is MACHINE_MCP_WORKSPACE or ~/machine-mcp-workspace. File tools cannot leave that root.

This does not replace Grok Bot Computers or Local execution. Those are a different control path. This server is the tool process on the machine they already use.

## How to use the tools

1. Call status first. Note OS, cwd, workspace, and whether copilot, ffmpeg, and git are on PATH.
2. Put demo scripts and output files in the workspace with write_file / read_file. Relative paths only.
3. Use run for commands that should execute in the workspace (copilot, git, ffmpeg, compilers). Pass a real argv string. Timeouts cap at 120 seconds.
4. record_terminal will not produce a video. On Linux, install ffmpeg if needed and run its suggested command yourself via run. Other platforms return an unsupported-platform error. Do not fake a recording.

## Never

- Never read SSH keys, Copilot config dirs, .env files, credential files, cookies, or token stores.
- Never run copilot login, gh auth login, or any login/device-code flow. Copilot CLI on this machine is already signed in. Use it.
- Never print, log, or echo secrets. run redacts github_pat_ and AWS key shapes if they leak into stdout. Do not try to bypass that.
- Never pass parent-directory segments or absolute paths to write_file / read_file.
- Never start an HTTP listener or bind a port. v1 is stdio only.
- Never git push or force-push unless the human explicitly asked in this turn.

## Copilot CLI demos

Record or script Copilot CLI demos on this machine because it is already signed in. Prefer run with copilot on PATH. Keep demo artifacts inside the workspace. If you need a screen capture, use the ffmpeg command from record_terminal on Linux. Do not pretend a file exists if you did not capture one.

## Token

A bearer token is printed to stderr on start. stdio does not require it. If HTTP is added later, send Authorization: Bearer $MACHINE_MCP_TOKEN. Do not put the token in status output or in workspace files.
