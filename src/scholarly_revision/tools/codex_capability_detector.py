'''Runtime detection for the installed, authenticated Codex CLI.'''

from __future__ import annotations

import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True, slots=True)
class CodexCapabilities:
    executable: str | None
    installed: bool
    version: str | None
    authentication_healthy: bool | None
    authentication_message: str
    exec_available: bool
    supports_jsonl: bool
    supports_output_schema: bool
    supports_output_last_message: bool
    supports_ephemeral: bool
    supports_cd: bool
    supports_sandbox: bool
    supports_color: bool
    supports_skip_git_repo_check: bool
    help_text_sha256: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _run(
    argv: list[str], *, timeout: float,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> subprocess.CompletedProcess[str]:
    return runner(
        argv, capture_output=True, text=True, encoding='utf-8',
        errors='replace', timeout=timeout, check=False, shell=False,
    )


def detect_codex_executable(configured_path: str | Path | None = None) -> Path | None:
    if configured_path:
        candidate = Path(configured_path).expanduser()
        if candidate.is_file():
            return candidate.resolve()
        return None
    discovered = shutil.which('codex')
    return Path(discovered).resolve() if discovered else None


def detect_codex_capabilities(
    configured_path: str | Path | None = None, *, timeout: float = 10,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> CodexCapabilities:
    executable = detect_codex_executable(configured_path)
    if executable is None:
        return CodexCapabilities(
            executable=None, installed=False, version=None,
            authentication_healthy=None,
            authentication_message='Codex executable was not found.',
            exec_available=False, supports_jsonl=False,
            supports_output_schema=False, supports_output_last_message=False,
            supports_ephemeral=False, supports_cd=False, supports_sandbox=False,
            supports_color=False, supports_skip_git_repo_check=False,
        )
    try:
        version_run = _run([str(executable), '--version'], timeout=timeout, runner=runner)
        help_run = _run([str(executable), 'exec', '--help'], timeout=timeout, runner=runner)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CodexCapabilities(
            executable=str(executable), installed=True, version=None,
            authentication_healthy=None,
            authentication_message=f'Codex capability check failed: {type(exc).__name__}.',
            exec_available=False, supports_jsonl=False,
            supports_output_schema=False, supports_output_last_message=False,
            supports_ephemeral=False, supports_cd=False, supports_sandbox=False,
            supports_color=False, supports_skip_git_repo_check=False,
        )
    help_text = (help_run.stdout or '') + (help_run.stderr or '')
    import hashlib
    digest = hashlib.sha256(help_text.encode('utf-8')).hexdigest()
    auth_ok: bool | None = None
    auth_message = 'Authentication status is unavailable in this CLI version.'
    try:
        auth_run = _run(
            [str(executable), 'login', 'status'], timeout=timeout, runner=runner,
        )
        auth_text = ((auth_run.stdout or '') + (auth_run.stderr or '')).strip()
        auth_ok = auth_run.returncode == 0
        auth_message = (
            'Authenticated Codex session detected.'
            if auth_ok else 'Codex is not authenticated; run codex login.'
        )
        if '403' in auth_text:
            auth_ok = False
            auth_message = 'Codex authentication was rejected (403); run codex login.'
    except (OSError, subprocess.TimeoutExpired):
        auth_message = 'Authentication status check timed out or could not run.'
    return CodexCapabilities(
        executable=str(executable), installed=True,
        version=(version_run.stdout or version_run.stderr).strip() or None,
        authentication_healthy=auth_ok,
        authentication_message=auth_message,
        exec_available=help_run.returncode == 0 and 'codex exec' in help_text.lower(),
        supports_jsonl='--json' in help_text,
        supports_output_schema='--output-schema' in help_text,
        supports_output_last_message='--output-last-message' in help_text,
        supports_ephemeral='--ephemeral' in help_text,
        supports_cd='--cd' in help_text,
        supports_sandbox='--sandbox' in help_text,
        supports_color='--color' in help_text,
        supports_skip_git_repo_check='--skip-git-repo-check' in help_text,
        help_text_sha256=digest,
    )
