'''One-shot local worker for a queued semantic task.'''
from __future__ import annotations
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from scholarly_revision.models.agent_run import AgentRunStatus
from scholarly_revision.models.agent_task import AgentTaskStatus
from scholarly_revision.services.agent_output_validation_service import (
    AgentOutputValidationService,
)
from scholarly_revision.services.agent_run_registry import AgentRunRegistry, _pid_alive
from scholarly_revision.services.agent_task_service import load_agent_settings
from scholarly_revision.services.codex_bridge_service import (
    CodexBridgeError, CodexBridgeService, classify_codex_failure,
)
from scholarly_revision.services.project_state_service import ProjectStateService
from scholarly_revision.services.project_workspace import sha256_file
from scholarly_revision.tools.codex_capability_detector import detect_codex_capabilities
from scholarly_revision.tools.structured_output_reader import (
    StructuredOutputError, read_structured_output,
)

def _now() -> datetime:
    return datetime.now(UTC)

@contextmanager
def _global_slot(limit: int, *, stale_after: float = 900):
    if limit != 1:
        raise ValueError('current local worker supports global concurrency of 1')
    path = Path(tempfile.gettempdir()) / 'scholarly-revision-agent-worker.lock'
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        try:
            lines = path.read_text(encoding='utf-8').splitlines()
            pid = int(lines[0])
            created = float(lines[1])
            alive = _pid_alive(pid)
        except (OSError, ValueError, IndexError):
            alive = False
            created = path.stat().st_mtime if path.exists() else 0
        if not alive and time.time() - created >= stale_after:
            path.unlink(missing_ok=True)
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        else:
            raise RuntimeError('GLOBAL_CONCURRENCY_LIMIT') from exc
    try:
        os.write(descriptor, f'{os.getpid()}\n{time.time()}'.encode())
        os.close(descriptor)
        yield
    finally:
        path.unlink(missing_ok=True)

class AgentWorkerService:
    def __init__(self, project_root: str | Path) -> None:
        self.root = Path(project_root).expanduser().resolve()
        self.registry = AgentRunRegistry(self.root)
        self.validator = AgentOutputValidationService(self.root)
        self.settings = load_agent_settings(self.root)
        self.state = ProjectStateService(self.root)

    def start_background(self, task_id: str) -> int:
        task = self.registry.load_task(task_id)
        if task.status is not AgentTaskStatus.QUEUED:
            raise ValueError('only a queued task can start a worker')
        script = Path(__file__).resolve().parents[3] / 'scripts' / 'agent_worker.py'
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        process = subprocess.Popen(
            [sys.executable, str(script), '--project-root', str(self.root),
             '--task-id', task_id],
            cwd=str(Path(__file__).resolve().parents[3]), stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            shell=False, creationflags=flags, close_fds=True,
        )
        return process.pid

    def run(self, task_id: str) -> int:
        task = self.registry.load_task(task_id)
        if task.status is not AgentTaskStatus.QUEUED or not task.active_run_id:
            raise ValueError('worker requires a queued task with a run')
        run = self.registry.load_run(task.active_run_id)
        try:
            with _global_slot(
                self.settings.global_concurrency,
                stale_after=self.settings.abandoned_run_seconds,
            ):
                return self._execute(task_id, run.run_id)
        except RuntimeError as exc:
            self._fail(task_id, run.run_id, str(exc), 'Another semantic task is active.')
            return 2

    def _execute(self, task_id: str, run_id: str) -> int:
        task = self.registry.load_task(task_id)
        run = self.registry.load_run(run_id)
        context = self.registry.load_context(task_id)
        run_dir = self.registry.run_dir(run_id)
        context_path = run_dir / 'context_manifest.json'
        expected = task.context_manifest_sha256
        task_context_path = self.registry.tasks_dir / f'{task_id}.context.json'
        if not task_context_path.is_file():
            self._fail(task_id, run_id, 'MISSING_CONTEXT', 'Approved context is missing.')
            return 2
        actual = hashlib.sha256(task_context_path.read_bytes()).hexdigest()
        if expected != actual:
            self._fail(task_id, run_id, 'SOURCE_HASH_MISMATCH', 'Approved context changed.')
            return 2
        for relative, digest in context.input_file_hashes.items():
            source = (self.root / relative).resolve()
            try:
                source.relative_to(self.root)
            except ValueError:
                self._fail(task_id, run_id, 'INVALID_INPUT_PATH', 'Context input escaped project.')
                return 2
            if not source.is_file():
                self._fail(task_id, run_id, 'MISSING_INPUT_FILE', relative)
                return 2
            if sha256_file(source) != digest:
                self._fail(task_id, run_id, 'SOURCE_HASH_MISMATCH', relative)
                return 2
        caps = detect_codex_capabilities(self.settings.codex_executable)
        if not caps.installed:
            self._fail(task_id, run_id, 'CODEX_NOT_INSTALLED', caps.authentication_message)
            return 2
        if not caps.exec_available:
            self._fail(task_id, run_id, 'CLI_VERSION_MISMATCH', 'codex exec is unavailable.')
            return 2
        if caps.authentication_healthy is False:
            self._fail(task_id, run_id, 'NOT_AUTHENTICATED', caps.authentication_message)
            return 2
        started = _now()
        running_run = run.model_copy(update={
            'status': AgentRunStatus.RUNNING, 'progress_percent': 10,
            'started_at': started, 'updated_at': started, 'worker_pid': os.getpid(),
            'codex_executable': caps.executable, 'codex_version': caps.version,
            'structured_mode': (
                'OUTPUT_SCHEMA_JSONL'
                if caps.supports_output_schema and caps.supports_jsonl
                else 'JSONL_FINAL_OBJECT' if caps.supports_jsonl else 'FINAL_JSON'
            ),
        })
        running_task = task.model_copy(update={
            'status': AgentTaskStatus.RUNNING, 'updated_at': started,
        })
        self.registry.save_run(running_run)
        self.registry.save_task(running_task)
        self._event('AGENT_RUN_STARTED', 'run_codex', running_task, run_id)
        bridge = CodexBridgeService(
            caps.executable, timeout_seconds=self.settings.default_timeout_seconds,
            capabilities=caps,
        )
        prompt = (run_dir / 'prompt.txt').read_text(encoding='utf-8')
        last_message = run_dir / 'raw_last_message.txt'
        temporary_last_message: Path | None = None
        if caps.supports_output_last_message:
            descriptor, temporary_name = tempfile.mkstemp(
                prefix='.codex-last-message-', suffix='.tmp', dir=run_dir,
            )
            os.close(descriptor)
            temporary_last_message = Path(temporary_name)
        try:
            result = bridge.execute(
                prompt=prompt, working_directory=run_dir,
                output_schema_path=run_dir / 'output_schema.json',
                output_last_message_path=temporary_last_message,
                cancellation_requested=lambda: self.registry.load_task(
                    task_id
                ).cancel_requested,
            )
        except CodexBridgeError as exc:
            if temporary_last_message and temporary_last_message.exists():
                os.replace(temporary_last_message, last_message)
            self._fail(task_id, run_id, exc.code, str(exc))
            return 2
        if temporary_last_message and temporary_last_message.exists():
            os.replace(temporary_last_message, last_message)
        self.registry.write_run_text(run_id, 'raw_stdout.txt', result.stdout)
        self.registry.write_run_text(run_id, 'raw_stderr.txt', result.stderr)
        if caps.supports_jsonl:
            self.registry.write_run_text(run_id, 'events.jsonl', result.stdout)
        ended = _now()
        completed = running_run.model_copy(update={
            'status': AgentRunStatus.COMPLETED_RAW, 'progress_percent': 60,
            'updated_at': ended, 'completed_at': ended,
            'duration_seconds': result.duration_seconds, 'exit_code': result.exit_code,
            'codex_pid': result.codex_pid,
        })
        self.registry.save_run(completed)
        self.registry.save_task(running_task.model_copy(update={
            'status': AgentTaskStatus.COMPLETED_RAW, 'updated_at': ended,
        }))
        parsing_details: dict[str, object] = {}
        parsed_raw = None
        parsing_error: str | None = None
        try:
            parsed_raw = read_structured_output(
                last_message_path=last_message if caps.supports_output_last_message else None,
                raw_stdout=result.stdout, jsonl=caps.supports_jsonl,
                schema=run_dir / 'output_schema.json',
                validation_details=parsing_details,
            )
        except (StructuredOutputError, OSError, ValueError) as exc:
            parsing_error = str(exc)
        if result.exit_code != 0 or result.timed_out or result.cancelled:
            code = classify_codex_failure(result)
            status = (
                AgentRunStatus.CANCELLED
                if result.cancelled else AgentRunStatus.FAILED
            )
            task_status = (
                AgentTaskStatus.CANCELLED
                if result.cancelled else AgentTaskStatus.FAILED
            )
            errors = [{
                'code': code,
                'message': 'Codex did not produce a successful result.',
            }]
            if parsing_error:
                errors.append({
                    'code': 'OUTPUT_DIAGNOSTIC',
                    'message': parsing_error,
                })
            self.registry.write_run_json(run_id, 'validation_report.json', {
                'valid': False, 'normalized_output': None,
                'errors': errors, 'warnings': [],
                'structured_output': parsing_details,
            })
            self._finish_failure(
                task_id, run_id, status, task_status, code,
                'Codex did not produce a successful result.',
            )
            return 2
        validating_at = _now()
        self.registry.save_run(completed.model_copy(update={
            'status': AgentRunStatus.VALIDATING, 'progress_percent': 75,
            'updated_at': validating_at,
        }))
        self.registry.save_task(self.registry.load_task(task_id).model_copy(update={
            'status': AgentTaskStatus.VALIDATING, 'updated_at': validating_at,
        }))
        if parsing_error or parsed_raw is None:
            report = {
                'valid': False, 'normalized_output': None,
                'errors': [{
                    'code': 'MALFORMED_OUTPUT',
                    'message': parsing_error or 'Codex final output is unavailable.',
                }],
                'warnings': [],
                'structured_output': parsing_details,
            }
            self.registry.write_run_json(run_id, 'validation_report.json', report)
            self._finish_failure(
                task_id, run_id, AgentRunStatus.FAILED, AgentTaskStatus.FAILED,
                'MALFORMED_OUTPUT',
                parsing_error or 'Codex final output is unavailable.',
            )
            return 2
        self.registry.write_run_json(run_id, 'raw_output.json', parsed_raw)
        validation = self.validator.validate(task, context, parsed_raw)
        report = validation.report()
        report['structured_output'] = parsing_details
        self.registry.write_run_json(run_id, 'validation_report.json', report)
        if not validation.valid or validation.normalized_output is None:
            codes = [item['code'] for item in report['errors']]
            self._finish_failure(
                task_id, run_id, AgentRunStatus.FAILED, AgentTaskStatus.FAILED,
                'SCHEMA_VALIDATION_FAILED', '; '.join(codes),
                validation_codes=codes,
            )
            return 2
        self.registry.write_run_json(
            run_id, 'validated_output.json', validation.normalized_output,
        )
        ready = _now()
        artifacts = {
            name: str((run_dir / name).relative_to(self.root).as_posix())
            for name in (
                'task.json', 'context_manifest.json', 'prompt.txt', 'prompt_hash.txt',
                'raw_stdout.txt', 'raw_stderr.txt', 'events.jsonl',
                'raw_last_message.txt', 'raw_output.json',
                'validated_output.json', 'validation_report.json',
                'author_decision.json', 'run_manifest.json',
            )
            if (run_dir / name).is_file()
        }
        approved_run = self.registry.load_run(run_id).model_copy(update={
            'status': AgentRunStatus.AUTHOR_REVIEW, 'progress_percent': 100,
            'updated_at': ready, 'validation_passed': True,
            'validation_error_codes': [], 'artifact_paths': artifacts,
        })
        approved_task = self.registry.load_task(task_id).model_copy(update={
            'status': AgentTaskStatus.AUTHOR_REVIEW, 'updated_at': ready,
        })
        self.registry.save_run(approved_run)
        self.registry.save_task(approved_task)
        self._event('AGENT_OUTPUT_VALIDATED', 'validate_agent_output', approved_task, run_id)
        return 0

    def _finish_failure(
        self, task_id, run_id, run_status, task_status, code, message,
        validation_codes=None,
    ) -> None:
        now = _now()
        run = self.registry.load_run(run_id).model_copy(update={
            'status': run_status, 'updated_at': now, 'progress_percent': 100,
            'validation_passed': False,
            'validation_error_codes': validation_codes or [code],
            'failure_code': code, 'failure_message': message,
        })
        task = self.registry.load_task(task_id).model_copy(update={
            'status': task_status, 'updated_at': now,
            'last_error_code': code, 'last_error_message': message,
        })
        self.registry.save_run(run)
        self.registry.save_task(task)
        self._event('AGENT_RUN_FAILED', 'agent_run_failed', task, run_id, code)

    def _fail(self, task_id: str, run_id: str, code: str, message: str) -> None:
        self._finish_failure(
            task_id, run_id, AgentRunStatus.FAILED, AgentTaskStatus.FAILED,
            code, message,
        )

    def _event(self, event_type, action, task, run_id, code=None) -> None:
        details = {
            'task_id': task.task_id, 'task_type': task.task_type.value,
            'task_status': task.status.value, 'run_id': run_id,
        }
        if code:
            details['failure_code'] = code
        self.state.record_event(
            event_type=event_type, action=action, actor='agent-worker', details=details,
        )
