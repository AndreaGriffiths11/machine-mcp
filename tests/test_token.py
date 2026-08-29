"""Token generation and secret redaction tests."""

import os
import shlex
import sys
import time
from pathlib import Path

import pytest

from machine_mcp.sandbox import SandboxError, resolve_in_workspace
from machine_mcp import server
from machine_mcp.server import build_status, get_or_create_token, redact_secrets


def test_uses_env_token(monkeypatch) -> None:
    monkeypatch.setenv("MACHINE_MCP_TOKEN", "fixed-test-token")
    assert get_or_create_token() == "fixed-test-token"


def test_generates_token_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("MACHINE_MCP_TOKEN", raising=False)
    token = get_or_create_token()
    assert token
    assert len(token) >= 32
    assert get_or_create_token() == token


def test_status_does_not_include_token(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MACHINE_MCP_TOKEN", "must-not-appear-in-status")
    monkeypatch.setenv("MACHINE_MCP_WORKSPACE", str(tmp_path))
    payload = build_status(tmp_path)
    dumped = str(payload)
    assert "must-not-appear-in-status" not in dumped
    assert "token" not in payload


def test_redact_github_pat() -> None:
    text = "export TOKEN=github_pat_abcdefghijklmnopqrstuvwxyz0123456789ABCD"
    out = redact_secrets(text)
    assert "github_pat_" in out
    assert "abcdefghijklmnopqrstuvwxyz0123456789ABCD" not in out
    assert "[REDACTED]" in out


def test_redact_aws_access_key() -> None:
    text = "aws_access_key_id=AKIA0000000000EXAMPLE"
    out = redact_secrets(text)
    assert "AKIA0000000000EXAMPLE" not in out
    assert "AKIA[REDACTED]" in out


def test_resolve_in_workspace_rejects_escapes(tmp_path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    with pytest.raises(SandboxError):
        resolve_in_workspace(root, "../escape")
    with pytest.raises(SandboxError):
        resolve_in_workspace(root, "/etc/passwd")


def test_run_reports_nonzero_exit_as_failure(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MACHINE_MCP_WORKSPACE", str(tmp_path))
    command = shlex.join([sys.executable, "-c", "raise SystemExit(7)"])

    result = server.run(command)

    assert result["ok"] is False
    assert result["exit_code"] == 7
    assert result["error"] == "command exited with code 7"


def test_run_caps_output(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MACHINE_MCP_WORKSPACE", str(tmp_path))
    monkeypatch.setattr(server, "RUN_OUTPUT_MAX_BYTES", 8)
    command = shlex.join([sys.executable, "-c", "print('abcdefghijk', end='')"])

    result = server.run(command)

    assert result["ok"] is True
    assert result["stdout"] == "abcdefgh"
    assert result["stdout_truncated"] is True
    assert result["stderr_truncated"] is False


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group behavior")
def test_run_timeout_kills_descendants(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MACHINE_MCP_WORKSPACE", str(tmp_path))
    child_code = "import pathlib,time; time.sleep(2); pathlib.Path('survived').write_text('yes')"
    parent_code = (
        "import subprocess,sys,time; "
        f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
        "time.sleep(20)"
    )
    command = shlex.join([sys.executable, "-c", parent_code])

    result = server.run(command, timeout_seconds=1)
    time.sleep(2)

    assert result["ok"] is False
    assert result["timed_out"] is True
    assert not (tmp_path / "survived").exists()


def test_record_terminal_does_not_suggest_linux_command_on_macos(monkeypatch) -> None:
    monkeypatch.setattr(server.shutil, "which", lambda _: "/usr/local/bin/ffmpeg")
    monkeypatch.setattr(server.platform, "system", lambda: "Darwin")

    result = server.record_terminal("echo demo")

    assert result["ok"] is False
    assert result["platform"] == "Darwin"
    assert "suggested_command" not in result
