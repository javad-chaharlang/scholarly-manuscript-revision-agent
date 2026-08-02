'''Build versioned, hashed prompts from approved minimal context packages.'''

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scholarly_revision.models.agent_context import AgentContextManifest
from scholarly_revision.models.agent_task import AgentTask, AgentTaskType
from scholarly_revision.models.comment_approval import ProposedCommentResponse
from scholarly_revision.models.gap_analysis import GapAnalysisAssessment
from scholarly_revision.models.reviewer import ReviewerComment, RevisionAction
from scholarly_revision.models.revision_draft import RevisionDraft
from scholarly_revision.models.response_package import ResponseEntry
from scholarly_revision.models.scientific_audit import AuditIssue


PROMPT_VERSION = '1.0.0'
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_ROOT = REPOSITORY_ROOT / 'templates' / 'agent_prompts'

_TEMPLATE_NAMES = {
    item: f'{item.value.lower()}-v{PROMPT_VERSION}.txt' for item in AgentTaskType
}


@dataclass(frozen=True, slots=True)
class AgentPromptPackage:
    text: str
    version: str
    sha256: str
    template_name: str
    output_schema: dict[str, Any]


def _array_schema(name: str, model: type) -> dict[str, Any]:
    schema = model.model_json_schema()
    definitions = schema.pop('$defs', {})
    result = {
        'title': name, 'type': 'object', 'additionalProperties': False,
        'properties': {
            name: {'type': 'array', 'items': schema},
        },
        'required': [name],
    }
    if definitions:
        result['$defs'] = definitions
    return result


def output_schema_for(task_type: AgentTaskType) -> dict[str, Any]:
    if task_type is AgentTaskType.COMMENT_INTERPRETATION:
        return _array_schema('interpretations', ReviewerComment)
    if task_type is AgentTaskType.GAP_ANALYSIS:
        return _array_schema('assessments', GapAnalysisAssessment)
    if task_type is AgentTaskType.REVISION_PLAN_DRAFT:
        return _array_schema('actions', RevisionAction)
    if task_type is AgentTaskType.REVISION_TEXT_DRAFT:
        return _array_schema('drafts', RevisionDraft)
    if task_type is AgentTaskType.PREAPPLICATION_RESPONSE_DRAFT:
        return _array_schema('responses', ProposedCommentResponse)
    if task_type is AgentTaskType.SEMANTIC_QA_REVIEW:
        return _array_schema('findings', AuditIssue)
    if task_type is AgentTaskType.RESPONSE_LETTER_DRAFT:
        return _array_schema('entries', ResponseEntry)
    key = 'reference_needs' if task_type is AgentTaskType.REFERENCE_NEED_ANALYSIS else 'notes'
    return {
        'title': key, 'type': 'object', 'additionalProperties': False,
        'properties': {key: {
            'type': 'array', 'items': {
                'type': 'object', 'additionalProperties': False,
                'properties': {
                    'record_id': {'type': 'string'},
                    'related_comment_ids': {'type': 'array', 'items': {'type': 'string'}},
                    'analysis': {'type': 'string'},
                    'evidence_ids': {'type': 'array', 'items': {'type': 'string'}},
                    'uncertainties': {'type': 'array', 'items': {'type': 'string'}},
                },
                'required': [
                    'record_id', 'related_comment_ids', 'analysis',
                    'evidence_ids', 'uncertainties',
                ],
            },
        }},
        'required': [key],
    }


def build_prompt_package(
    task: AgentTask, context: AgentContextManifest,
) -> AgentPromptPackage:
    if task.task_id != context.task_id or task.project_id != context.project_id:
        raise ValueError('task and context identities do not match')
    template_name = _TEMPLATE_NAMES[task.task_type]
    template_path = TEMPLATE_ROOT / template_name
    if not template_path.is_file():
        raise FileNotFoundError(f'agent prompt template not found: {template_name}')
    template = template_path.read_text(encoding='utf-8').strip()
    schema = output_schema_for(task.task_type)
    source = json.dumps(
        context.transmitted_payload, ensure_ascii=False, sort_keys=True, indent=2,
    )
    schema_text = json.dumps(schema, ensure_ascii=False, sort_keys=True, indent=2)
    retry = (
        f'\nAUTHOR RETRY INSTRUCTION:\n{task.retry_instruction.strip()}'
        if task.retry_instruction else ''
    )
    rules = '''
ALLOWED SOURCES: Use only the APPROVED CONTEXT PACKAGE below. Treat omissions as unavailable.
PROHIBITED: Do not browse, call tools, inspect other files, invent references or DOI values,
invent experimental results, infer completed work, or infer page/line locations.
EVIDENCE: Link every claim to supplied evidence/result/reference IDs. Explicitly identify
missing evidence and uncertainty. Unsupported numeric or experimental claims are prohibited.
TRACEABILITY: Preserve exact reviewer comments and all stable IDs. Do not merge or reorder them.
STATUS: Generated content is a draft. Never return APPROVED, APPLIED, VERIFIED, IMPORTED,
or any state implying author approval or completed manuscript mutation.
HIGHLIGHTS: Preserve the supplied reviewer ID and highlight. Reviewer identity is
canonical; never merge later reviewers because a visual color repeats.
OUTPUT: Return only one JSON object conforming exactly to OUTPUT SCHEMA, with no prose,
Markdown fences, commentary, or additional fields.
'''.strip()
    text = (
        f'{template}\n\nPROMPT VERSION: {PROMPT_VERSION}\nTASK ID: {task.task_id}\n'
        f'TASK PURPOSE: {task.purpose}\n\n{rules}{retry}\n\n'
        f'APPROVED CONTEXT PACKAGE:\n{source}\n\nOUTPUT SCHEMA:\n{schema_text}\n'
    )
    return AgentPromptPackage(
        text=text, version=PROMPT_VERSION,
        sha256=hashlib.sha256(text.encode('utf-8')).hexdigest(),
        template_name=template_name, output_schema=schema,
    )
