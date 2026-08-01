'''Inspect Codex locally; the optional live probe uses synthetic content only.'''
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Callable

from scholarly_revision.services.codex_bridge_service import (
    CodexBridgeError, CodexBridgeService,
)
from scholarly_revision.tools.codex_capability_detector import (
    CodexCapabilities, detect_codex_capabilities,
)
from scholarly_revision.tools.structured_output_reader import (
    StructuredOutputError, read_structured_output,
)

_EXPECTED = {
    'status': 'ok',
    'message': 'Codex bridge operational',
}
_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'properties': {
        'status': {'type': 'string', 'enum': ['ok']},
        'message': {
            'type': 'string',
            'enum': ['Codex bridge operational'],
        },
    },
    'required': ['status', 'message'],
}
_PROMPT = (
    'Anonymous synthetic health check. Return exactly this JSON object and no '
    'other content: '
    + json.dumps(_EXPECTED, separators=(',', ':'))
    + '. Do not read files, call tools, browse, or include any other fields.'
)


def _failure_report(
    *, message: str, exit_code: int | None = None,
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    diagnostics = details or {}
    return {
        'status': 'error',
        'message': message,
        'health': 'LIVE_TEST_FAILED',
        'exit_code': exit_code,
        'schema_valid': diagnostics.get('schema_valid', False),
        'safe_event_types': diagnostics.get('safe_event_types', []),
        'last_message': {
            'exists': diagnostics.get('last_message_exists', False),
            'bytes': diagnostics.get('last_message_bytes', 0),
        },
    }


def run_live_health(
    capabilities: CodexCapabilities, *,
    bridge_factory: Callable[..., CodexBridgeService] = CodexBridgeService,
) -> tuple[dict[str, object], int]:
    '''Run one anonymous synthetic request and return a safe report and exit code.'''
    if (
        not capabilities.installed or not capabilities.exec_available
        or capabilities.authentication_healthy is False
    ):
        return _failure_report(message='Codex CLI is not ready for a live check.'), 2

    with tempfile.TemporaryDirectory(prefix='codex-anonymous-health-') as raw:
        root = Path(raw)
        prompt_path = root / 'prompt.txt'
        schema_path = root / 'schema.json'
        prompt_path.write_text(_PROMPT, encoding='utf-8')
        schema_path.write_text(json.dumps(_SCHEMA), encoding='utf-8')
        last_message: Path | None = None
        if capabilities.supports_output_last_message:
            descriptor, temporary_name = tempfile.mkstemp(
                prefix='last-message-', suffix='.json', dir=root,
            )
            os.close(descriptor)
            last_message = Path(temporary_name)
        try:
            result = bridge_factory(
                capabilities=capabilities, timeout_seconds=60,
            ).execute(
                prompt=prompt_path.read_text(encoding='utf-8'),
                working_directory=root,
                output_schema_path=schema_path,
                output_last_message_path=last_message,
            )
        except (CodexBridgeError, OSError) as exc:
            return _failure_report(
                message='Codex live execution could not start.',
                details={'failure_type': type(exc).__name__},
            ), 2

        details: dict[str, object] = {}
        parsed = None
        parse_error = None
        try:
            parsed = read_structured_output(
                last_message_path=last_message,
                raw_stdout=result.stdout,
                jsonl=capabilities.supports_jsonl,
                schema=schema_path,
                validation_details=details,
            )
        except (StructuredOutputError, OSError, ValueError) as exc:
            parse_error = str(exc)
        if result.exit_code != 0:
            return _failure_report(
                message='Codex exited unsuccessfully.',
                exit_code=result.exit_code, details=details,
            ), 2
        if parse_error or parsed != _EXPECTED:
            return _failure_report(
                message=parse_error or 'Codex returned an unexpected response.',
                exit_code=result.exit_code, details=details,
            ), 2
        return {**_EXPECTED, 'health': 'READY'}, 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--codex-executable')
    args = parser.parse_args()
    capabilities = detect_codex_capabilities(args.codex_executable)
    if args.live:
        report, exit_code = run_live_health(capabilities)
    else:
        ready = (
            capabilities.installed and capabilities.exec_available
            and capabilities.authentication_healthy is not False
        )
        report = {
            'health': 'READY' if ready else 'NOT_READY',
            'installed': capabilities.installed,
            'version': capabilities.version,
            'supports_jsonl': capabilities.supports_jsonl,
            'supports_output_schema': capabilities.supports_output_schema,
            'supports_output_last_message': capabilities.supports_output_last_message,
        }
        exit_code = 0 if ready else 2
    print(json.dumps(report, indent=2))
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
