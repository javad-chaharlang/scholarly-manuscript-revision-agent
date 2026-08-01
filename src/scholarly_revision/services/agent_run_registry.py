'''Atomic file-based task/run registry inside each confidential project.'''
from __future__ import annotations
import json
import os
import tempfile
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator
from scholarly_revision.models.agent_context import AgentContextManifest
from scholarly_revision.models.agent_run import AgentRun, AgentRunStatus
from scholarly_revision.models.agent_task import AgentTask, AgentTaskStatus

TERMINAL_TASKS = {
    AgentTaskStatus.IMPORTED, AgentTaskStatus.REJECTED, AgentTaskStatus.FAILED,
    AgentTaskStatus.CANCELLED, AgentTaskStatus.BLOCKED,
}
ACTIVE_RUNS = {AgentRunStatus.QUEUED, AgentRunStatus.RUNNING, AgentRunStatus.VALIDATING}

def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.stem + '-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write('\n')
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise

def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.stem + '-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(value)
        os.replace(temporary, path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise

class RegistryLockError(TimeoutError):
    pass

class AgentRunRegistry:
    def __init__(self, project_root: str | Path) -> None:
        self.root = Path(project_root).expanduser().resolve()
        self.tasks_dir = self.root / 'working' / 'agent_tasks'
        self.runs_dir = self.root / 'agent_runs'
        self.lock_dir = self.root / 'audit' / 'agent_locks'
        for directory in (self.tasks_dir, self.runs_dir, self.lock_dir):
            directory.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def lock(self, name: str, *, timeout: float = 5, stale_after: float = 3600) -> Iterator[None]:
        path = self.lock_dir / f'{name}.lock'
        deadline = time.monotonic() + timeout
        while True:
            try:
                descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(descriptor, f'{os.getpid()}\n{time.time()}'.encode())
                os.close(descriptor)
                break
            except FileExistsError:
                if path.exists() and time.time() - path.stat().st_mtime > stale_after:
                    path.unlink(missing_ok=True)
                    continue
                if time.monotonic() >= deadline:
                    raise RegistryLockError(f'agent registry lock is busy: {name}')
                time.sleep(0.05)
        try:
            yield
        finally:
            path.unlink(missing_ok=True)

    def task_path(self, task_id: str) -> Path:
        return self.tasks_dir / f'{task_id}.json'

    def run_dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id

    def save_task(self, task: AgentTask) -> Path:
        with self.lock(task.task_id):
            _atomic_json(self.task_path(task.task_id), task.model_dump(mode='json'))
        return self.task_path(task.task_id)

    def add_task(self, task: AgentTask) -> Path:
        if self.task_path(task.task_id).exists():
            raise FileExistsError(f'duplicate task ID: {task.task_id}')
        return self.save_task(task)

    def load_task(self, task_id: str) -> AgentTask:
        path = self.task_path(task_id)
        if not path.is_file():
            raise FileNotFoundError(f'agent task not found: {task_id}')
        return AgentTask.model_validate_json(path.read_text(encoding='utf-8'))

    def tasks(self) -> list[AgentTask]:
        return sorted(
            (AgentTask.model_validate_json(path.read_text(encoding='utf-8'))
             for path in self.tasks_dir.glob('TASK-*.json')
             if not path.name.endswith('.context.json')),
            key=lambda item: (item.created_at, item.task_id), reverse=True,
        )

    def find_duplicate(self, candidate: AgentTask) -> AgentTask | None:
        for task in self.tasks():
            if task.retry_of_task_id:
                continue
            if (
                task.task_type == candidate.task_type
                and task.related_comment_ids == candidate.related_comment_ids
                and task.related_action_ids == candidate.related_action_ids
                and task.source_element_ids == candidate.source_element_ids
                and task.status not in {AgentTaskStatus.REJECTED, AgentTaskStatus.CANCELLED}
            ):
                return task
        return None

    def save_context(self, manifest: AgentContextManifest) -> Path:
        path = self.tasks_dir / f'{manifest.task_id}.context.json'
        _atomic_json(path, manifest.model_dump(mode='json'))
        return path

    def load_context(self, task_id: str) -> AgentContextManifest:
        path = self.tasks_dir / f'{task_id}.context.json'
        if not path.is_file():
            raise FileNotFoundError(f'agent context not found: {task_id}')
        return AgentContextManifest.model_validate_json(path.read_text(encoding='utf-8'))

    def create_run(
        self, run: AgentRun, task: AgentTask, context: AgentContextManifest,
        *, prompt: str, output_schema: dict[str, Any],
    ) -> Path:
        directory = self.run_dir(run.run_id)
        with self.lock('project-active-run'):
            if any(item.status in ACTIVE_RUNS for item in self.runs()):
                raise ValueError('another semantic task is already active for this project')
            if directory.exists():
                raise FileExistsError(f'duplicate run ID: {run.run_id}')
            directory.mkdir(parents=True)
            _atomic_json(directory / 'task.json', task.model_dump(mode='json'))
            _atomic_json(directory / 'context_manifest.json', context.model_dump(mode='json'))
            _write_text(directory / 'prompt.txt', prompt)
            _write_text(directory / 'prompt_hash.txt', run.prompt_sha256 + '\n')
            _atomic_json(directory / 'output_schema.json', output_schema)
            _atomic_json(directory / 'author_decision.json', {
                'decision': None, 'decision_maker': None,
                'decision_timestamp': None, 'approval_inferred': False,
            })
            self.save_run(run)
        return directory

    def save_run(self, run: AgentRun) -> Path:
        path = self.run_dir(run.run_id) / 'run_manifest.json'
        _atomic_json(path, run.model_dump(mode='json'))
        return path

    def load_run(self, run_id: str) -> AgentRun:
        path = self.run_dir(run_id) / 'run_manifest.json'
        if not path.is_file():
            raise FileNotFoundError(f'agent run not found: {run_id}')
        return AgentRun.model_validate_json(path.read_text(encoding='utf-8'))

    def runs(self) -> list[AgentRun]:
        runs = []
        for path in self.runs_dir.glob('RUN-*/run_manifest.json'):
            try:
                runs.append(AgentRun.model_validate_json(path.read_text(encoding='utf-8')))
            except (OSError, ValueError):
                continue
        return sorted(runs, key=lambda item: (item.created_at, item.run_id), reverse=True)

    def write_run_text(self, run_id: str, name: str, value: str) -> Path:
        allowed = {
            'raw_stdout.txt', 'raw_stderr.txt', 'events.jsonl',
            'prompt.txt', 'prompt_hash.txt',
        }
        if name not in allowed:
            raise ValueError(f'unsupported run text artifact: {name}')
        path = self.run_dir(run_id) / name
        _write_text(path, value)
        return path

    def write_run_json(self, run_id: str, name: str, value: Any) -> Path:
        allowed = {
            'raw_output.json', 'validated_output.json', 'validation_report.json',
            'author_decision.json', 'run_manifest.json', 'task.json',
            'context_manifest.json', 'output_schema.json',
        }
        if name not in allowed:
            raise ValueError(f'unsupported run JSON artifact: {name}')
        path = self.run_dir(run_id) / name
        _atomic_json(path, value)
        return path

    def recover_interrupted(self, *, stale_seconds: float = 60) -> list[str]:
        recovered: list[str] = []
        now = datetime.now(UTC)
        for run in self.runs():
            if run.status is not AgentRunStatus.RUNNING:
                continue
            age = (now - run.updated_at).total_seconds()
            alive = False
            if run.worker_pid:
                alive = _pid_alive(run.worker_pid)
            if alive or age < stale_seconds:
                continue
            updated = run.model_copy(update={
                'status': AgentRunStatus.RECOVERY_REQUIRED,
                'updated_at': now, 'failure_code': 'INTERRUPTED_PROCESS',
                'failure_message': 'Worker stopped; explicit retry or cancellation is required.',
            })
            self.save_run(updated)
            task = self.load_task(run.task_id)
            self.save_task(task.model_copy(update={
                'status': AgentTaskStatus.BLOCKED, 'updated_at': now,
                'last_error_code': 'RECOVERY_REQUIRED',
                'last_error_message': 'Interrupted run requires an explicit author action.',
            }))
            recovered.append(run.run_id)
        return recovered


def _pid_alive(pid: int) -> bool:
    if os.name != 'nt':
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    try:
        import ctypes
        process = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not process:
            return False
        ctypes.windll.kernel32.CloseHandle(process)
        return True
    except (AttributeError, OSError):
        return False
