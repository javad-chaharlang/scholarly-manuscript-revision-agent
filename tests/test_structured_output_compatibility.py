from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_codex_health import run_live_health
from scholarly_revision.services.codex_bridge_service import CodexExecutionResult
from scholarly_revision.tools.codex_capability_detector import CodexCapabilities
from scholarly_revision.tools.structured_output_reader import (
    StructuredOutputError,
    read_one_json_object,
    read_structured_output,
)


_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'properties': {
        'status': {'type': 'string', 'enum': ['ok']},
        'message': {'type': 'string'},
    },
    'required': ['status', 'message'],
}


def _capabilities() -> CodexCapabilities:
    return CodexCapabilities(
        executable='mock-codex', installed=True, version='codex-cli mocked',
        authentication_healthy=True, authentication_message='mock',
        exec_available=True, supports_jsonl=True, supports_output_schema=True,
        supports_output_last_message=True, supports_ephemeral=True,
        supports_cd=True, supports_sandbox=True, supports_color=True,
        supports_skip_git_repo_check=True, help_text_sha256='0' * 64,
    )


def _completed(
    payload: dict[str, object], *, kind: str = 'agent_message',
    type_key: str = 'type',
) -> str:
    return json.dumps({
        'type': 'item.completed',
        'item': {type_key: kind, 'text': json.dumps(payload)},
    })


def test_current_item_completed_agent_message_format() -> None:
    assert read_structured_output(
        raw_stdout=_completed({'value': 1}), jsonl=True,
    ) == {'value': 1}


def test_legacy_assistant_message_format() -> None:
    assert read_structured_output(
        raw_stdout=_completed({'value': 2}, kind='assistant_message'),
        jsonl=True,
    ) == {'value': 2}


@pytest.mark.parametrize('kind', ['agent_message', 'assistant_message'])
def test_item_type_variants(kind: str) -> None:
    assert read_structured_output(
        raw_stdout=_completed({'kind': kind}, kind=kind, type_key='item_type'),
        jsonl=True,
    ) == {'kind': kind}


def test_top_level_agent_message_event() -> None:
    event = json.dumps({
        'type': 'agent_message',
        'text': json.dumps({'value': 'top-level'}),
    })
    assert read_structured_output(raw_stdout=event, jsonl=True) == {
        'value': 'top-level',
    }


def test_multiple_messages_select_last_completed_nonempty_message() -> None:
    events = [
        json.dumps({'type': 'thread.started', 'thread_id': 'synthetic'}),
        _completed({'value': 'first'}),
        json.dumps({
            'type': 'item.completed',
            'item': {'type': 'reasoning', 'text': json.dumps({'wrong': 1})},
        }),
        json.dumps({
            'type': 'item.completed',
            'item': {'type': 'command_execution', 'text': json.dumps({'wrong': 2})},
        }),
        _completed({'value': 'last'}),
        json.dumps({'type': 'turn.completed', 'usage': {'input_tokens': 1}}),
    ]
    assert read_structured_output(
        raw_stdout='\n'.join(events), jsonl=True,
    ) == {'value': 'last'}


def test_valid_last_message_is_canonical_without_jsonl_message(tmp_path: Path) -> None:
    last_message = tmp_path / 'last.json'
    last_message.write_text(json.dumps({'status': 'ok', 'message': 'ready'}))
    details: dict[str, object] = {}
    output = read_structured_output(
        last_message_path=last_message,
        raw_stdout=json.dumps({'type': 'turn.completed'}),
        jsonl=True, schema=_SCHEMA, validation_details=details,
    )
    assert output == {'status': 'ok', 'message': 'ready'}
    assert details['source'] == 'last_message'
    assert details['last_message_bytes'] > 0


def test_empty_last_message_uses_valid_jsonl_fallback(tmp_path: Path) -> None:
    last_message = tmp_path / 'last.json'
    last_message.write_text('')
    details: dict[str, object] = {}
    output = read_structured_output(
        last_message_path=last_message,
        raw_stdout=_completed({'status': 'ok', 'message': 'fallback'}),
        jsonl=True, schema=_SCHEMA, validation_details=details,
    )
    assert output['message'] == 'fallback'
    assert details['source'] == 'jsonl'
    assert details['last_message_empty'] is True


def test_malformed_jsonl_line_is_reported_before_valid_event() -> None:
    details: dict[str, object] = {}
    output = read_structured_output(
        raw_stdout='not-json\n' + _completed({'value': 'valid'}),
        jsonl=True, validation_details=details,
    )
    assert output == {'value': 'valid'}
    assert details['malformed_jsonl_lines'] == [{
        'line': 1, 'error': 'JSON decode error at column 1',
    }]


def test_strict_jsonl_rejects_malformed_line() -> None:
    with pytest.raises(StructuredOutputError, match='line 1'):
        read_structured_output(
            raw_stdout='not-json\n' + _completed({'value': 'valid'}),
            jsonl=True, strict_jsonl=True,
        )


def test_no_final_message_fails_clearly(tmp_path: Path) -> None:
    last_message = tmp_path / 'last.json'
    last_message.write_text('')
    events = '\n'.join([
        json.dumps({'type': 'thread.started'}),
        json.dumps({'type': 'turn.started'}),
        json.dumps({
            'type': 'item.completed',
            'item': {'type': 'reasoning', 'text': 'synthetic'},
        }),
        json.dumps({'type': 'turn.completed'}),
    ])
    with pytest.raises(StructuredOutputError, match='final output is empty'):
        read_structured_output(
            last_message_path=last_message, raw_stdout=events, jsonl=True,
        )


def test_fenced_json_parsing() -> None:
    fence = chr(96) * 3
    fenced = fence + 'json\n' + json.dumps({'status': 'ok'}) + '\n' + fence
    assert read_one_json_object(fenced) == {'status': 'ok'}


def test_explanation_followed_by_one_json_object() -> None:
    text = 'Synthetic result follows.\n' + json.dumps({'status': 'ok'})
    assert read_one_json_object(text) == {'status': 'ok'}


def test_conflicting_multiple_json_objects_are_rejected() -> None:
    text = json.dumps({'status': 'ok'}) + '\n' + json.dumps({'status': 'error'})
    with pytest.raises(StructuredOutputError, match='multiple conflicting'):
        read_one_json_object(text)


def test_schema_invalid_response_is_rejected() -> None:
    details: dict[str, object] = {}
    with pytest.raises(StructuredOutputError, match='requested schema'):
        read_structured_output(
            raw_stdout=_completed({'status': 'ok'}),
            jsonl=True, schema=_SCHEMA, validation_details=details,
        )
    assert details['schema_valid'] is False
    assert details['schema_errors'] == [{
        'path': '$', 'validator': 'required',
    }]


@pytest.mark.parametrize('exit_code, expected_health', [(0, 'READY'), (9, 'LIVE_TEST_FAILED')])
def test_live_health_uses_mocked_codex_and_honors_exit_code(
    exit_code: int, expected_health: str,
) -> None:
    class MockBridge:
        def __init__(self, **kwargs) -> None:
            del kwargs

        def execute(self, **kwargs) -> CodexExecutionResult:
            output = kwargs['output_last_message_path']
            assert output is not None
            Path(output).write_text(json.dumps({
                'status': 'ok',
                'message': 'Codex bridge operational',
            }), encoding='utf-8')
            return CodexExecutionResult(
                argv=('mock-codex', 'exec', '-'),
                exit_code=exit_code,
                stdout=json.dumps({'type': 'turn.completed'}),
                stderr='anonymous synthetic diagnostic',
                duration_seconds=0.01,
            )

    report, code = run_live_health(
        _capabilities(), bridge_factory=MockBridge,
    )
    assert report['health'] == expected_health
    assert code == (0 if exit_code == 0 else 2)
    if exit_code:
        assert report['exit_code'] == exit_code
