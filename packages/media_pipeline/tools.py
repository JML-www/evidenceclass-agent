"""Project-local FFmpeg/FFprobe discovery and shell-free execution."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .errors import MediaToolExecutionError, MediaToolUnavailableError

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: bytes
    stderr: bytes


class CommandRunner(Protocol):
    def run(self, args: Sequence[str], *, timeout_seconds: float) -> CommandResult: ...


class SubprocessCommandRunner:
    """Execute an argument vector directly; media paths never pass through a shell."""

    def run(self, args: Sequence[str], *, timeout_seconds: float) -> CommandResult:
        try:
            completed = subprocess.run(
                list(args),
                check=False,
                capture_output=True,
                timeout=timeout_seconds,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise MediaToolExecutionError(
                "media tool could not complete",
                details={"tool": Path(args[0]).name, "reason": type(exc).__name__},
            ) from exc
        return CommandResult(
            args=tuple(str(item) for item in args),
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


def resolve_media_tool(name: str, explicit: str | Path | None = None) -> Path:
    """Resolve a tool from explicit config, environment, the ignored runtime, or PATH."""

    if name not in {"ffmpeg", "ffprobe"}:
        raise ValueError("only ffmpeg and ffprobe are supported")
    suffix = ".exe" if os.name == "nt" else ""
    env_name = f"EVIDENCECLASS_{name.upper()}_PATH"
    candidates: list[Path] = []
    configured = explicit or os.getenv(env_name)
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.append(REPOSITORY_ROOT / ".media-runtime" / "bin" / f"{name}{suffix}")
    discovered = shutil.which(name)
    if discovered:
        candidates.append(Path(discovered))
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_file():
            return resolved
    raise MediaToolUnavailableError(
        f"{name} is unavailable; run scripts/setup-media-tools.ps1 or configure {env_name}"
    )


def sanitized_stderr(result: CommandResult, *, limit: int = 600) -> str:
    """Return a bounded diagnostic without leaking a full command or media path."""

    text = result.stderr.decode("utf-8", errors="replace").strip()
    return text[-limit:]
