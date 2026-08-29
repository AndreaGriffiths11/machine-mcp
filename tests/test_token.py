"""Token generation and secret redaction tests."""

import pytest

from machine_mcp.sandbox import SandboxError, resolve_in_workspace
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
