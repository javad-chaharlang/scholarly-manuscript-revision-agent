'''Safe, version-adaptive subprocess bridge to an authenticated Codex CLI.'''

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from scholarly_revision.tools.codex_capability_detector import (
    CodexCapabilities, detect_codex_capabilities,
)


@dataclass(frozen=True, slots=True)
class CodexExecutionResult:
    argv: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    cancelled: bool = False
    codex_pid: int | None = None
    structured_mode: str = 'FINAL_JSON'


class CodexBridgeError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def classify_codex_failure(result: CodexExecutionResult) -> str:
    combined = (result.stderr + '\n' + result.stdout).casefold()
    if result.cancelled:
        return 'USER_CANCELLED'
    if result.timed_out:
        return 'TASK_TIMEOUT'
    if '403' in combined or 'forbidden' in combined:
        return 'AUTHORIZATION_403'
    if 'not logged in' in combined or 'authentication' in combined:
        return 'NOT_AUTHENTICATED'
    if 'network' in combined or 'timed out' in combined:
        return 'NETWORK_TIMEOUT'
    return 'CODEX_EXIT_NONZERO'


class CodexBridgeService:
    def __init__(
        self, executable: str | Path | None = None, *, timeout_seconds: int = 600,
        capabilities: CodexCapabilities | None = None,
        popen_factory: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
    ) -> None:
        self.capabilities = capabilities or detect_codex_capabilities(executable)
        self.timeout_seconds = timeout_seconds
        self._popen = popen_factory

    def build_command(
        self, *, working_directory: str | Path,
        output_schema_path: str | Path | None = None,
        output_last_message_path: str | Path | None = None,
    ) -> list[str]:
        caps = self.capabilities
        if not caps.installed or not caps.executable:
            raise CodexBridgeError('CODEX_NOT_INSTALLED', 'Codex CLI is not installed.')
        if not caps.exec_available:
            raise CodexBridgeError(
                'CLI_VERSION_MISMATCH', 'Installed Codex CLI does not support codex exec.',
            )
        root = Path(working_directory).resolve()
        if not root.is_dir():
            raise CodexBridgeError('INVALID_WORKING_DIRECTORY', 'Codex working directory is missing.')
        argv = [caps.executable, 'exec']
        if caps.supports_cd:
            argv.extend(['--cd', str(root)])
        if caps.supports_skip_git_repo_check:
            argv.append('--skip-git-repo-check')
        if caps.supports_sandbox:
            argv.extend(['--sandbox', 'read-only'])
        if caps.supports_ephemeral:
            argv.append('--ephemeral')
        if caps.supports_jsonl:
            argv.append('--json')
        if output_schema_path and caps.supports_output_schema:
            schema = Path(output_schema_path).resolve()
            if not schema.is_file():
                raise CodexBridgeError('MISSING_OUTPUT_SCHEMA', 'Output schema file is missing.')
            argv.extend(['--output-schema', str(schema)])
        if output_last_message_path and caps.supports_output_last_message:
            argv.extend(['--output-last-message', str(Path(output_last_message_path).resolve())])
        if caps.supports_color:
            argv.extend(['--color', 'never'])
        argv.append('-')
        return argv

    def execute(
        self, *, prompt: str, working_directory: str | Path,
        output_schema_path: str | Path | None = None,
        output_last_message_path: str | Path | None = None,
        timeout_seconds: int | None = None,
        cancellation_requested: Callable[[], bool] | None = None,
    ) -> CodexExecutionResult:
        if not prompt.strip():
            raise CodexBridgeError('EMPTY_PROMPT', 'Codex prompt cannot be empty.')
        argv = self.build_command(
            working_directory=working_directory,
            output_schema_path=output_schema_path,
            output_last_message_path=output_last_message_path,
        )
        started = time.monotonic()
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        try:
            process = self._popen(
                argv, cwd=str(Path(working_directory).resolve()),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding='utf-8', errors='replace', shell=False,
                creationflags=creation_flags,
            )
        except OSError as exc:
            raise CodexBridgeError('CODEX_LAUNCH_FAILED', type(exc).__name__) from exc
        limit = timeout_seconds or self.timeout_seconds
        first = True
        timed_out = False
        cancelled = False
        stdout = stderr = ''
        while True:
            if cancellation_requested and cancellation_requested():
                cancelled = True
                process.terminate()
                break
            elapsed = time.monotonic() - started
            if elapsed >= limit:
                timed_out = True
                process.terminate()
                break
            try:
                stdout, stderr = process.communicate(
                    input=prompt if first else None,
                    timeout=min(0.25, max(0.01, limit - elapsed)),
                )
                break
            except subprocess.TimeoutExpired:
                first = False
                continue
        if timed_out or cancelled:
            try:
                stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
        return CodexExecutionResult(
            argv=tuple(argv), exit_code=int(process.returncode or 0),
            stdout=stdout or '', stderr=stderr or '',
            duration_seconds=time.monotonic() - started,
            timed_out=timed_out, cancelled=cancelled,
            codex_pid=getattr(process, 'pid', None),
            structured_mode=(
                'OUTPUT_SCHEMA_JSONL' if self.capabilities.supports_output_schema
                and self.capabilities.supports_jsonl
                else 'JSONL_FINAL_OBJECT' if self.capabilities.supports_jsonl
                else 'FINAL_JSON'
            ),
        )

    def health(self) -> CodexCapabilities:
        '''Return local installation/auth metadata without a model request.'''
        return self.capabilities
