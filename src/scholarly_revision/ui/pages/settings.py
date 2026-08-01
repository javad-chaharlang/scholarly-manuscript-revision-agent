from __future__ import annotations
import json
import tempfile
from pathlib import Path
import streamlit as st
from scholarly_revision.services.agent_task_service import (
    AgentSettings, load_agent_settings, save_agent_settings,
)
from scholarly_revision.services.codex_bridge_service import CodexBridgeService
from scholarly_revision.tools.codex_capability_detector import detect_codex_capabilities
from scholarly_revision.tools.structured_output_reader import read_structured_output
from scholarly_revision.ui.components import page_title
from scholarly_revision.ui.state import redact_exception

@st.cache_data(ttl='30s', max_entries=8)
def _capabilities(executable: str | None) -> dict:
    return detect_codex_capabilities(executable or None).to_dict()

def _safe_smoke(executable: str | None) -> tuple[bool, str]:
    caps = detect_codex_capabilities(executable or None)
    schema_value = {
        'type': 'object', 'additionalProperties': False,
        'properties': {'status': {'type': 'string', 'enum': ['ok']}},
        'required': ['status'],
    }
    with tempfile.TemporaryDirectory(prefix='codex-anonymous-ui-smoke-') as raw:
        root = Path(raw)
        schema = root / 'schema.json'
        schema.write_text(json.dumps(schema_value), encoding='utf-8')
        output = root / 'output.json'
        result = CodexBridgeService(
            executable or None, timeout_seconds=60, capabilities=caps,
        ).execute(
            prompt=(
                'Anonymous synthetic smoke test. Return only a JSON object '
                'with status equal to ok. Do not browse or use files.'
            ),
            working_directory=root, output_schema_path=schema,
            output_last_message_path=output,
        )
        parsed = read_structured_output(
            last_message_path=output, raw_stdout=result.stdout,
            jsonl=caps.supports_jsonl,
        )
        passed = result.exit_code == 0 and parsed == {'status': 'ok'}
        return passed, f'exit code {result.exit_code}; schema valid: {passed}'

def render(orchestrator, project_root, actor) -> None:
    page_title(
        'Settings',
        'Local storage settings and an authenticated Codex CLI bridge; '
        'no API key is required or displayed.',
    )
    st.session_state['actor'] = st.text_input(
        'Default decision maker', value=st.session_state.get('actor', actor),
    )
    st.text_input(
        'Workspace root', value=st.session_state.get('workspace_root', ''),
        disabled=True,
    )
    if orchestrator is not None:
        st.text_input('Registry file', value=str(orchestrator.registry.path), disabled=True)
    st.subheader('Required highlight policy')
    st.table([
        {'scope': 'Reviewer 1', 'color': 'Yellow'},
        {'scope': 'Reviewer 2', 'color': 'Bright Green'},
        {'scope': 'Shared/general', 'color': 'Violet'},
    ])
    st.subheader('Agent Settings')
    root = Path(project_root) if project_root else None
    settings = load_agent_settings(root) if root else AgentSettings()
    with st.form('agent_settings_form', border=True):
        executable = st.text_input(
            'Codex executable path', value=settings.codex_executable or '',
            help='Leave blank to detect codex on PATH.',
        )
        timeout = st.number_input(
            'Default timeout (seconds)', min_value=10, max_value=3600,
            value=settings.default_timeout_seconds, step=10,
        )
        warning_size = st.number_input(
            'Context-size warning threshold (characters)', min_value=1000,
            max_value=2000000, value=settings.context_warning_characters, step=1000,
        )
        concurrency = st.number_input(
            'Global concurrency', min_value=1, max_value=1,
            value=settings.global_concurrency,
            help='Phase 10 permits one local semantic task globally by default.',
        )
        pilot = st.toggle('Pilot Mode default', value=settings.pilot_mode)
        allow = st.toggle('Allow semantic tasks', value=settings.allow_semantic_tasks)
        saved = st.form_submit_button(
            'Save Agent Settings', icon=':material/save:', disabled=root is None,
        )
    if saved and root:
        try:
            save_agent_settings(root, AgentSettings(
                codex_executable=executable.strip() or None,
                default_timeout_seconds=int(timeout),
                context_warning_characters=int(warning_size),
                global_concurrency=int(concurrency), pilot_mode=pilot,
                allow_semantic_tasks=allow,
                one_active_task_per_project=True, abandoned_run_seconds=60,
            ))
            _capabilities.clear()
            st.success('Agent settings saved in the project workspace.')
        except Exception as exc:
            st.error(redact_exception(exc))
    st.warning(
        'Transmission warning: selected project excerpts leave local storage only '
        'after APPROVE_TRANSMISSION. Review every exact context package first.',
        icon=':material/privacy_tip:',
    )
    audit_location = root / 'agent_runs' if root else 'Select a project'
    st.caption(f'Local audit location: {audit_location}')
    with st.container(horizontal=True):
        test = st.button('Test Codex Connection', icon=':material/cable:')
        smoke = st.button(
            'Run Safe JSON Smoke Test', icon=':material/science:',
            help='Sends anonymous synthetic text only; this is a live Codex request.',
        )
        redetect = st.button(
            'Re-detect Capabilities', icon=':material/refresh:',
        )
    if redetect:
        _capabilities.clear()
    caps = _capabilities(executable.strip() or None)
    if test or redetect:
        st.success('Local Codex installation and authentication status checked.')
    st.json({
        'Codex executable': caps.get('executable'),
        'detected version': caps.get('version'),
        'authentication health': caps.get('authentication_healthy'),
        'authentication message': caps.get('authentication_message'),
        'supported exec capabilities': {
            key: value for key, value in caps.items() if key.startswith('supports_')
        },
        'exec available': caps.get('exec_available'),
    }, expanded=True)
    if smoke:
        try:
            passed, detail = _safe_smoke(executable.strip() or None)
            if passed:
                st.success(f'Anonymous JSON smoke test passed ({detail}).')
            else:
                st.error(f'Anonymous JSON smoke test failed ({detail}).')
        except Exception as exc:
            st.error(redact_exception(exc))
    st.info(
        'No OpenAI API key is used. Codex authentication is managed by the '
        'currently authenticated CLI session. Tokens are never displayed.'
    )
