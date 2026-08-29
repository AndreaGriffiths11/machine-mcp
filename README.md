# machine-mcp

A laptop-side MCP server. An AI agent talks to it over stdio and runs tools on the human's own machine (the one already signed into Copilot CLI and the rest of the local toolchain).

This is a local command process. It does not wrap Cursor or Grok Bot pairing. It does not replace Grok Bot Computers or Local execution.

## Install

Python 3.10 or newer.

```bash
cd machine-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Dev tests:

```bash
pip install -e ".[dev]"
pytest tests/
```

## Run

```bash
machine-mcp
```

stdio servers block on stdin. The client starts the process and owns the pipes.

Smoke test (prints status JSON, exits 0):

```bash
machine-mcp --check
```

On start, if `MACHINE_MCP_TOKEN` is unset, a random bearer token is generated and printed once to stderr:

```
machine-mcp token: ...
```

Keep that token for HTTP v2. stdio v1 does not check it: the client already spawned this process as you.

## Cursor / Grok Bot connector

Add a local MCP server whose command is the venv entry point. No pairing protocol.

```json
{
  "mcpServers": {
    "machine-mcp": {
      "command": "path/to/.venv/bin/machine-mcp"
    }
  }
}
```

See `examples/mcp.json`. Point `command` at the absolute path of `.venv/bin/machine-mcp` on this laptop.

Optional env:

- `MACHINE_MCP_WORKSPACE` file-tool root. Default: `~/machine-mcp-workspace` (created on start).
- `MACHINE_MCP_TOKEN` bearer token for a future HTTP listener. Generated if unset.

## Tools

| Tool | What it does |
| --- | --- |
| `status` | OS, hostname, cwd, Python version, whether `copilot` / `ffmpeg` / `git` exist on PATH. No secrets. |
| `run` | `subprocess` in the workspace root. `shlex.split`, not `shell=True`. Default timeout 30s, max 120s. Nonzero exits return `ok: false`; stdout and stderr are capped at 1MB each. Timed-out process groups are terminated. Redacts `github_pat_` and AWS access-key shapes in output. |
| `record_terminal` | Honest stub that never writes a video file. On Linux with `ffmpeg`, returns an `x11grab` command; other platforms return a clear unsupported-platform error. |
| `write_file` | Write a path relative to the workspace. Refuses `..` and absolute paths. |
| `read_file` | Read a path relative to the workspace. Same sandbox. 1MB limit. |

## Local only

stdio is local to this process. There is no listen socket in v1. HTTP is optional later and must require `MACHINE_MCP_TOKEN`. Do not expose this server on a network.

## License

MIT. Copyright Andrea Griffiths 2026.
