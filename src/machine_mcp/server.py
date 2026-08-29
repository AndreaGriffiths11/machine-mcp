"""machine-mcp stdio server.

stdio is local to the process the client spawned. There is no pairing protocol.
HTTP is not implemented in v1. MACHINE_MCP_TOKEN is generated now so a future
HTTP listener can require Authorization: Bearer <token>.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import secrets
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, BinaryIO

from mcp.server.mcpserver import MCPServer

from machine_mcp.sandbox import SandboxError, resolve_in_workspace

READ_FILE_MAX_BYTES = 1_000_000
RUN_OUTPUT_MAX_BYTES = 1_000_000
DEFAULT_TIMEOUT = 30
MAX_TIMEOUT = 120
DEFAULT_WORKSPACE = Path.home() / "machine-mcp-workspace"

# github_pat_ plus common AWS access-key id shape (AKIAxxxxxxxxxxxxxxxx)
_GITHUB_PAT = re.compile(r"github_pat_[A-Za-z0-9_]{20,}")
_AWS_ACCESS_KEY = re.compile(r"AKIA[0-9A-Z]{16}")
_AWS_SECRET = re.compile(
    r"(?i)(?:aws_secret_access_key|aws secret)[\"'\s:=]+([A-Za-z0-9/+=]{40})"
)

mcp = MCPServer("machine-mcp", version="0.1.0")


def get_or_create_token() -> str:
    """Return MACHINE_MCP_TOKEN, generating one if unset."""
    existing = os.environ.get("MACHINE_MCP_TOKEN", "").strip()
    if existing:
        return existing
    token = secrets.token_urlsafe(32)
    os.environ["MACHINE_MCP_TOKEN"] = token
    return token


def get_workspace() -> Path:
    """Workspace root from MACHINE_MCP_WORKSPACE, default ~/machine-mcp-workspace."""
    raw = os.environ.get("MACHINE_MCP_WORKSPACE", "").strip()
    root = Path(raw).expanduser() if raw else DEFAULT_WORKSPACE
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def redact_secrets(text: str) -> str:
    """Redact GitHub PATs and AWS keys from tool output."""
    if not text:
        return text
    redacted = _GITHUB_PAT.sub("github_pat_[REDACTED]", text)
    redacted = _AWS_ACCESS_KEY.sub("AKIA[REDACTED]", redacted)
    redacted = _AWS_SECRET.sub(lambda m: m.group(0)[: m.start(1) - m.start(0)] + "[REDACTED]", redacted)
    return redacted


def _which(name: str) -> bool:
    return shutil.which(name) is not None


def _read_process_output(stream: BinaryIO) -> tuple[str, bool]:
    stream.seek(0)
    data = stream.read(RUN_OUTPUT_MAX_BYTES + 1)
    truncated = len(data) > RUN_OUTPUT_MAX_BYTES
    text = data[:RUN_OUTPUT_MAX_BYTES].decode("utf-8", "replace")
    return redact_secrets(text), truncated


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return

    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError:
            process.kill()
    elif os.name == "nt":
        completed = subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if completed.returncode != 0 and process.poll() is None:
            process.kill()
    else:
        process.kill()

    process.wait()


def build_status(workspace: Path | None = None) -> dict[str, Any]:
    """Machine status. No secrets, no home listing."""
    ws = workspace if workspace is not None else get_workspace()
    return {
        "os": platform.system(),
        "hostname": socket.gethostname(),
        "cwd": os.getcwd(),
        "python_version": platform.python_version(),
        "workspace": str(ws),
        "transport": "stdio",
        "tools_on_path": {
            "copilot": _which("copilot"),
            "ffmpeg": _which("ffmpeg"),
            "git": _which("git"),
        },
    }


def _refuse_dotdot(user_path: str) -> None:
    parts = Path(user_path).parts
    if ".." in parts:
        raise SandboxError("parent-directory path segments are not allowed")


@mcp.tool()
def status() -> dict[str, Any]:
    """Report OS, hostname, cwd, Python version, and whether copilot, ffmpeg, and git are on PATH.

    Does not return secrets, tokens, or a home-directory listing.
    """
    return build_status()


@mcp.tool()
def run(command: str, timeout_seconds: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Run a command in the workspace root (not a shell).

    Args:
        command: Program and arguments as a single string. Split with shlex on POSIX.
        timeout_seconds: Kill after this many seconds. Default 30, max 120.

    Output is limited to 1MB each for stdout and stderr. A nonzero exit code
    returns ok=false.
    """
    if command is None or not str(command).strip():
        return {"ok": False, "error": "command is empty"}

    try:
        timeout = int(timeout_seconds)
    except (TypeError, ValueError):
        return {"ok": False, "error": "timeout_seconds must be an integer"}
    if timeout <= 0:
        return {"ok": False, "error": "timeout_seconds must be positive"}
    timeout = min(timeout, MAX_TIMEOUT)

    try:
        argv = shlex.split(command, posix=os.name != "nt")
    except ValueError as exc:
        return {"ok": False, "error": f"could not parse command: {exc}"}
    if not argv:
        return {"ok": False, "error": "command is empty"}

    workspace = get_workspace()
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        popen_options: dict[str, Any] = {}
        if os.name == "posix":
            popen_options["start_new_session"] = True
        elif os.name == "nt":
            popen_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        try:
            process = subprocess.Popen(
                argv,
                cwd=workspace,
                stdout=stdout_file,
                stderr=stderr_file,
                shell=False,
                **popen_options,
            )
        except FileNotFoundError:
            return {
                "ok": False,
                "error": f"executable not found: {argv[0]}",
                "exit_code": None,
            }
        except OSError as exc:
            return {"ok": False, "error": str(exc), "exit_code": None}

        timed_out = False
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_process_tree(process)

        stdout, stdout_truncated = _read_process_output(stdout_file)
        stderr, stderr_truncated = _read_process_output(stderr_file)

    if timed_out:
        return {
            "ok": False,
            "error": f"timed out after {timeout}s",
            "stdout": stdout,
            "stderr": stderr,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
            "exit_code": None,
            "timed_out": True,
        }

    ok = process.returncode == 0
    result = {
        "ok": ok,
        "stdout": stdout,
        "stderr": stderr,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
        "exit_code": process.returncode,
        "timed_out": False,
    }
    if not ok:
        result["error"] = f"command exited with code {process.returncode}"
    return result


@mcp.tool()
def record_terminal(script: str) -> dict[str, Any]:
    """Record a bash script as a terminal demo.

    This host does not start a recorder. If ffmpeg is missing, returns an error.
    If ffmpeg is present, returns the command you would run (Linux x11grab) and
    does not write a video file.
    """
    if script is None or not str(script).strip():
        return {"ok": False, "error": "script is empty"}

    system = platform.system()
    if system != "Linux":
        return {
            "ok": False,
            "error": f"terminal recording is not implemented on {system}",
            "detail": (
                "machine-mcp will not suggest a Linux capture command on this host "
                "or claim that it wrote a video."
            ),
            "platform": system,
            "script_length": len(script),
        }

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return {
            "ok": False,
            "error": "ffmpeg is not on PATH. Install ffmpeg before recording a terminal session.",
        }

    display = os.environ.get("DISPLAY", ":0.0")
    suggested = (
        f"{ffmpeg} -y -f x11grab -video_size 1920x1080 -i {display} "
        f"-c:v libx264 -pix_fmt yuv420p terminal-demo.mp4"
    )
    return {
        "ok": False,
        "error": "not implemented on this host yet",
        "detail": (
            "machine-mcp will not start a recorder or write a fake video. "
            "Run the suggested ffmpeg command yourself on Linux if you need a capture."
        ),
        "suggested_command": suggested,
        "platform": system,
        "script_length": len(script),
    }


@mcp.tool()
def write_file(path: str, content: str) -> dict[str, Any]:
    """Write a UTF-8 file relative to the workspace root.

    Refuses absolute paths and parent-directory segments.
    """
    if content is None:
        content = ""
    try:
        _refuse_dotdot(path)
        target = resolve_in_workspace(get_workspace(), path)
    except SandboxError as exc:
        return {"ok": False, "error": str(exc)}

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "error": str(exc)}

    return {"ok": True, "path": str(target.relative_to(get_workspace())), "bytes": len(content.encode("utf-8"))}


@mcp.tool()
def read_file(path: str) -> dict[str, Any]:
    """Read a UTF-8 file relative to the workspace root. Size limit 1MB.

    Refuses absolute paths and parent-directory segments.
    """
    try:
        _refuse_dotdot(path)
        target = resolve_in_workspace(get_workspace(), path)
    except SandboxError as exc:
        return {"ok": False, "error": str(exc)}

    if not target.exists() or not target.is_file():
        return {"ok": False, "error": "file not found"}

    try:
        size = target.stat().st_size
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    if size > READ_FILE_MAX_BYTES:
        return {
            "ok": False,
            "error": f"file larger than {READ_FILE_MAX_BYTES} bytes",
            "size": size,
        }

    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {"ok": False, "error": "file is not valid UTF-8"}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}

    return {"ok": True, "path": str(target.relative_to(get_workspace())), "content": content}


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="machine-mcp",
        description=(
            "Laptop-side MCP server. stdio transport is local to this process. "
            "This does not replace Grok Bot Computers or local execution pairing."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Print status JSON to stdout and exit 0. Does not start the stdio loop.",
    )
    args = parser.parse_args()

    workspace = get_workspace()
    token = get_or_create_token()
    print(f"machine-mcp token: {token}", file=sys.stderr)

    if args.check:
        json.dump(build_status(workspace), sys.stdout, indent=2)
        sys.stdout.write("\n")
        return

    print(
        "machine-mcp: stdio transport (local process only). HTTP auth is not implemented.",
        file=sys.stderr,
    )
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
