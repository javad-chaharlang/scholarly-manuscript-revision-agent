'''Safe structured-response parsing for current and legacy Codex CLI output.'''

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, MutableMapping

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


_MESSAGE_TYPES = {'agent_message', 'assistant_message'}


class StructuredOutputError(ValueError):
    pass


def _text(value: str | bytes) -> str:
    return value.decode('utf-8', errors='strict') if isinstance(value, bytes) else value


def _object_candidates(text: str) -> list[tuple[int, int, dict[str, Any]]]:
    '''Return non-nested JSON objects embedded in otherwise harmless text.'''
    decoder = json.JSONDecoder()
    candidates: list[tuple[int, int, dict[str, Any]]] = []
    for start, character in enumerate(text):
        if character != '{':
            continue
        try:
            decoded, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict):
            candidates.append((start, end, decoded))
    return [
        candidate for candidate in candidates
        if not any(
            other[0] < candidate[0] and other[1] >= candidate[1]
            for other in candidates
        )
    ]


def read_one_json_object(value: str | bytes) -> dict[str, Any]:
    '''Read one JSON object, allowing a fence or harmless leading explanation.'''
    text = _text(value)
    stripped = text.strip()
    if not stripped:
        raise StructuredOutputError('agent output is empty')
    try:
        decoded = json.loads(stripped)
    except json.JSONDecodeError:
        candidates = _object_candidates(text)
        if not candidates:
            raise StructuredOutputError('agent output contains no valid JSON object')
        distinct = {
            json.dumps(item[2], ensure_ascii=False, sort_keys=True, separators=(',', ':'))
            for item in candidates
        }
        if len(candidates) > 1 and len(distinct) > 1:
            raise StructuredOutputError('agent output contains multiple conflicting JSON objects')
        decoded = candidates[-1][2]
    if not isinstance(decoded, dict):
        raise StructuredOutputError('agent output must be one JSON object')
    return decoded


def _safe_event_type(event: dict[str, Any]) -> str:
    event_type = event.get('type')
    label = event_type if isinstance(event_type, str) and event_type else '<missing>'
    item = event.get('item')
    if isinstance(item, dict):
        item_type = item.get('type') or item.get('item_type')
        if isinstance(item_type, str) and item_type:
            return f'{label}/{item_type}'
    return label


def _message_text(event: dict[str, Any]) -> str | None:
    '''Return only completed agent/assistant messages, never tool-like content.'''
    event_type = event.get('type')
    item = event.get('item')
    if event_type == 'item.completed' and isinstance(item, dict):
        item_type = item.get('type') or item.get('item_type')
        if item_type in _MESSAGE_TYPES:
            for key in ('text', 'content'):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    return value
        return None

    top_level_type = event_type or event.get('item_type')
    if top_level_type in _MESSAGE_TYPES and event.get('status') not in {
        'started', 'in_progress', 'updated',
    }:
        for key in ('text', 'content', 'message'):
            value = event.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return None


def _inspect_codex_jsonl(
    value: str | bytes, *, strict: bool, details: MutableMapping[str, Any],
) -> list[str]:
    text = _text(value)
    messages: list[str] = []
    malformed: list[dict[str, Any]] = []
    invalid_events: list[dict[str, Any]] = []
    safe_types: list[str] = []
    nonempty_lines = 0
    valid_events = 0
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        nonempty_lines += 1
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            malformed.append({
                'line': number, 'error': f'JSON decode error at column {exc.colno}',
            })
            if strict:
                details.update({
                    'jsonl_line_count': nonempty_lines,
                    'jsonl_valid_event_count': valid_events,
                    'malformed_jsonl_lines': malformed,
                    'invalid_jsonl_events': invalid_events,
                    'safe_event_types': safe_types,
                    'agent_message_count': len(messages),
                })
                raise StructuredOutputError(
                    f'malformed Codex JSONL event on line {number}'
                ) from exc
            continue
        if not isinstance(event, dict):
            invalid_events.append({'line': number, 'error': 'event is not an object'})
            if strict:
                raise StructuredOutputError(f'Codex JSONL event {number} is not an object')
            continue
        valid_events += 1
        event_label = _safe_event_type(event)
        if event_label not in safe_types:
            safe_types.append(event_label)
        message = _message_text(event)
        if message is not None:
            messages.append(message)
    details.update({
        'jsonl_line_count': nonempty_lines,
        'jsonl_valid_event_count': valid_events,
        'malformed_jsonl_lines': malformed,
        'invalid_jsonl_events': invalid_events,
        'safe_event_types': safe_types,
        'agent_message_count': len(messages),
    })
    return messages


def _load_schema(schema: dict[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(schema, dict):
        return schema
    try:
        decoded = json.loads(Path(schema).read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise StructuredOutputError('requested output schema is unreadable or invalid') from exc
    if not isinstance(decoded, dict):
        raise StructuredOutputError('requested output schema must be a JSON object')
    return decoded


def _validate_schema(
    output: dict[str, Any], schema: dict[str, Any] | str | Path,
    details: MutableMapping[str, Any],
) -> None:
    requested = _load_schema(schema)
    try:
        Draft202012Validator.check_schema(requested)
    except SchemaError as exc:
        details['schema_valid'] = False
        details['schema_errors'] = [{'path': '$', 'validator': 'invalid_schema'}]
        raise StructuredOutputError('requested output schema is not a valid JSON Schema') from exc
    errors = sorted(
        Draft202012Validator(requested).iter_errors(output),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    )
    if errors:
        safe_errors = []
        for error in errors:
            path = '$' + ''.join(
                f'[{part}]' if isinstance(part, int) else f'.{part}'
                for part in error.absolute_path
            )
            safe_errors.append({'path': path, 'validator': str(error.validator)})
        details['schema_valid'] = False
        details['schema_errors'] = safe_errors
        first = safe_errors[0]
        message = 'agent output does not conform to the requested schema at %s (%s)' % (
            first['path'], first['validator'],
        )
        raise StructuredOutputError(message)
    details['schema_valid'] = True
    details['schema_errors'] = []


def read_codex_jsonl(
    value: str | bytes, *, strict: bool = False,
    schema: dict[str, Any] | str | Path | None = None,
    validation_details: MutableMapping[str, Any] | None = None,
) -> dict[str, Any]:
    details = validation_details if validation_details is not None else {}
    messages = _inspect_codex_jsonl(value, strict=strict, details=details)
    if not messages:
        raise StructuredOutputError('Codex JSONL contains no completed agent message')
    details['source'] = 'jsonl'
    output = read_one_json_object(messages[-1])
    if schema is not None:
        _validate_schema(output, schema, details)
    return output


def read_structured_output(
    *, last_message_path: str | Path | None = None,
    raw_stdout: str = '', jsonl: bool = False, strict_jsonl: bool = False,
    schema: dict[str, Any] | str | Path | None = None,
    validation_details: MutableMapping[str, Any] | None = None,
) -> dict[str, Any]:
    '''Read canonical last-message output, falling back to compatible JSONL.'''
    details = validation_details if validation_details is not None else {}
    path = Path(last_message_path) if last_message_path is not None else None
    exists = bool(path and path.is_file())
    size = path.stat().st_size if exists and path is not None else 0
    details.update({
        'source': None,
        'last_message_requested': path is not None,
        'last_message_exists': exists,
        'last_message_bytes': size,
        'last_message_empty': not size,
        'schema_valid': None,
        'schema_errors': [],
    })

    messages = (
        _inspect_codex_jsonl(raw_stdout, strict=strict_jsonl, details=details)
        if jsonl else []
    )
    if exists and size and path is not None:
        output = read_one_json_object(path.read_bytes())
        details['source'] = 'last_message'
    elif jsonl and messages:
        output = read_one_json_object(messages[-1])
        details['source'] = 'jsonl'
    elif not jsonl and raw_stdout.strip():
        output = read_one_json_object(raw_stdout)
        details['source'] = 'stdout'
    else:
        raise StructuredOutputError(
            'Codex final output is empty: the last-message file was unavailable or '
            'empty and JSONL contains no completed agent message'
        )
    if schema is not None:
        _validate_schema(output, schema, details)
    return output
