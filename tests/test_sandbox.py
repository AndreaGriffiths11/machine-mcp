"""Tests for resolve_in_workspace."""

from pathlib import Path

import pytest

from machine_mcp.sandbox import SandboxError, resolve_in_workspace


def test_rejects_dotdot_escape(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (tmp_path / "secret.txt").write_text("nope", encoding="utf-8")
    with pytest.raises(SandboxError, match="escapes"):
        resolve_in_workspace(root, "../secret.txt")


def test_rejects_nested_dotdot_escape(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    (root / "sub").mkdir(parents=True)
    with pytest.raises(SandboxError, match="escapes"):
        resolve_in_workspace(root, "sub/../../outside.txt")


def test_rejects_absolute_etc_passwd(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    with pytest.raises(SandboxError, match="absolute"):
        resolve_in_workspace(root, "/etc/passwd")


def test_valid_nested_file(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    nested = root / "a" / "b"
    nested.mkdir(parents=True)
    target = nested / "c.txt"
    target.write_text("ok", encoding="utf-8")
    resolved = resolve_in_workspace(root, "a/b/c.txt")
    assert resolved == target.resolve()
    assert resolved.is_relative_to(root.resolve())


def test_valid_path_need_not_exist(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    resolved = resolve_in_workspace(root, "new/dir/file.txt")
    assert resolved == (root / "new" / "dir" / "file.txt").resolve()
    assert resolved.is_relative_to(root.resolve())


def test_empty_path_rejected(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    with pytest.raises(SandboxError, match="empty"):
        resolve_in_workspace(root, "")
    with pytest.raises(SandboxError, match="empty"):
        resolve_in_workspace(root, "   ")
