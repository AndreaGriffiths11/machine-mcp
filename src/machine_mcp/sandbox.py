"""Path sandbox: keep file tools inside a workspace root."""

from __future__ import annotations

from pathlib import Path


class SandboxError(ValueError):
    """Raised when a path is empty, absolute, or resolves outside the workspace."""


def resolve_in_workspace(root: Path | str, user_path: str) -> Path:
    """Resolve user_path under root.

    Raises SandboxError if the path is empty, absolute, or the resolved
    location is outside root (including parent-directory escapes and symlink jumps).
    The target does not need to exist.
    """
    if user_path is None:
        raise SandboxError("path is empty")
    if not isinstance(user_path, str):
        raise SandboxError("path must be a string")
    stripped = user_path.strip()
    if not stripped:
        raise SandboxError("path is empty")
    if "\x00" in stripped:
        raise SandboxError("path contains NUL")

    raw = Path(stripped)
    if raw.is_absolute():
        raise SandboxError("absolute paths are not allowed")

    root_resolved = Path(root).expanduser().resolve()
    candidate = (root_resolved / stripped).resolve()

    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise SandboxError(f"path escapes workspace: {user_path}") from exc

    return candidate
