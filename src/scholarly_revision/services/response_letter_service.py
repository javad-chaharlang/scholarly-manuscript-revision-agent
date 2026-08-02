'''Prepare and strictly import source-grounded response-letter packages.'''

from __future__ import annotations

from collections import defaultdict
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scholarly_revision.models.enums import EvidenceStatus, ReviewerSource
from scholarly_revision.models.response_package import (
    EditorCoverLetter, LocationStatus, ResponseEntry, ResponsePackage, ResponseStatus,
    ReviewerResponseSection,
)
from scholarly_revision.models.reviewer import (
    ReviewerComment,
    RevisionAction,
    highlight_for_reviewer_number,
)
from scholarly_revision.models.revision_draft import ChangeRecord, RevisionDraft
from scholarly_revision.services.config_loader import load_project_manifest
from scholarly_revision.services.comment_approval_service import approved_response_map
from scholarly_revision.services.gap_analysis_service import read_json, write_json
from scholarly_revision.services.project_workspace import sha256_file
from scholarly_revision.tools.location_verifier import verify_locations


def _optional_json(path: Path, default: Any) -> Any:
    return read_json(path) if path.is_file() else default


def _registry(root: Path, names: tuple[str, ...]) -> list[dict[str, Any]]:
    for name in names:
        for directory in ('working', 'audit', 'config'):
            path = root / directory / name
            if not path.is_file():
                continue
            payload = read_json(path)
            if isinstance(payload, list):
                return [dict(item) for item in payload]
            if isinstance(payload, dict):
                for key in ('records', 'evidence', 'references', 'results'):
                    if isinstance(payload.get(key), list):
                        return [dict(item) for item in payload[key]]
    return []


def load_response_sources(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).expanduser().resolve()
    comments_raw = read_json(root / 'working' / 'reviewer_comments.json')
    plan = read_json(root / 'working' / 'revision_plan.json')
    change_payload = _optional_json(root / 'audit' / 'change_log.json', {'changes': []})
    drafts_payload = _optional_json(root / 'working' / 'revision_drafts.json', {'drafts': []})
    comments = [ReviewerComment.model_validate(item) for item in comments_raw]
    actions = [RevisionAction.model_validate(item) for item in plan.get('actions', [])]
    changes = [
        ChangeRecord.model_validate(item) for item in change_payload.get('changes', [])
    ]
    drafts = [
        RevisionDraft.model_validate(item['draft'])
        for item in drafts_payload.get('drafts', [])
        if isinstance(item, dict) and isinstance(item.get('draft'), dict)
    ]
    return {
        'root': root,
        'comments': comments,
        'actions': actions,
        'changes': changes,
        'drafts': drafts,
        'evidence': _registry(root, ('evidence_registry.json', 'evidence_records.json')),
        'references': _registry(root, ('reference_registry.json', 'references.json')),
        'results': _registry(root, ('results_registry.json', 'experimental_results.json')),
        'qa': _optional_json(root / 'audit' / 'scientific_qa_report.json', {}),
    }


def _location_for(change: ChangeRecord) -> list[str]:
    locations = []
    if change.target_section:
        locations.append(f'Section {change.target_section}')
    target = change.target_element_id or ''
    if target.startswith('PAR-'):
        locations.append(f'Paragraph {target}')
    elif match := re.fullmatch(r'FIG-(\d+)', target):
        locations.append(f'Figure {int(match.group(1))}')
    return list(dict.fromkeys(locations))


def build_response_drafting_package(project_root: str | Path) -> dict[str, Any]:
    '''Create deterministic context with deliberately blank response prose.'''

    sources = load_response_sources(project_root)
    root = sources['root']
    manifest = load_project_manifest(root / 'config' / 'project_manifest.yaml')
    actions: list[RevisionAction] = sources['actions']
    changes: list[ChangeRecord] = sources['changes']
    drafts: list[RevisionDraft] = sources['drafts']
    evidence = {str(item.get('evidence_id')): item for item in sources['evidence']}
    references = {str(item.get('reference_id')): item for item in sources['references']}
    preapproved_responses = approved_response_map(root)
    entries = []
    for number, comment in enumerate(sources['comments'], start=1):
        linked_actions = [item for item in actions if comment.comment_id in item.comment_ids]
        linked_changes = [item for item in changes if comment.comment_id in item.comment_ids]
        linked_drafts = [item for item in drafts if comment.comment_id in item.comment_ids]
        evidence_ids = list(dict.fromkeys(
            value for item in linked_actions for value in item.evidence_ids
        ))
        reference_ids = list(dict.fromkeys(
            value for item in linked_drafts for value in item.reference_ids
        ))
        candidates = list(dict.fromkeys(
            location for item in linked_changes for location in _location_for(item)
        ))
        manuscript = root / 'outputs' / 'Revised_Manuscript_Highlighted.docx'
        location_results = (
            verify_locations(manuscript, candidates)
            if manuscript.is_file() and candidates else []
        )
        verified_locations = [
            item.location for item in location_results if item.verified
        ]
        location_status = LocationStatus.NOT_REQUIRED
        if verified_locations:
            location_status = (
                LocationStatus.OBJECT_VERIFIED
                if any(item.status is LocationStatus.OBJECT_VERIFIED for item in location_results)
                else LocationStatus.SECTION_VERIFIED
            )
        elif linked_changes:
            location_status = LocationStatus.UNVERIFIED
        entries.append({
            'response_entry_id': f'RESP-{number:04d}',
            'reviewer_source': comment.reviewer_source.value,
            'reviewer_number': comment.reviewer_number,
            'comment_id': comment.comment_id,
            'sequence_number': comment.sequence_number,
            'exact_comment': comment.original_comment,
            'approved_interpretation': comment.interpretation,
            'approved_actions': [
                item.model_dump(mode='json') for item in linked_actions
                if item.approval_state.value == 'APPROVED'
            ],
            'applied_changes': [
                item.model_dump(mode='json') for item in linked_changes
                if item.verification_status == 'VERIFIED'
            ],
            'verified_evidence': [
                evidence[item_id] for item_id in evidence_ids
                if item_id in evidence and str(evidence[item_id].get('status')) == 'VERIFIED'
            ],
            'verified_references': [
                references[item_id] for item_id in reference_ids
                if item_id in references and references[item_id].get('bibliographic_verified') is True
            ],
            'verified_locations': verified_locations,
            'unresolved_limitations': list(dict.fromkeys(
                value for item in linked_actions for value in item.unresolved_questions
            )),
            'author_response': preapproved_responses.get(comment.comment_id, ''),
            'changes_made': '',
            'related_action_ids': [item.action_id for item in linked_actions],
            'related_change_ids': [item.change_id for item in linked_changes],
            'related_evidence_ids': evidence_ids,
            'related_reference_ids': reference_ids,
            'highlight': comment.highlight.value,
            'response_status': (
                'AUTHOR_REVIEW'
                if comment.comment_id in preapproved_responses
                else 'NOT_STARTED'
            ),
            'location_status': location_status.value,
            'evidence_status': (
                EvidenceStatus.VERIFIED.value if evidence_ids and all(
                    item_id in evidence and str(evidence[item_id].get('status')) == 'VERIFIED'
                    for item_id in evidence_ids
                ) else (
                    EvidenceStatus.MISSING.value if evidence_ids
                    else EvidenceStatus.NOT_REQUIRED.value
                )
            ),
            'author_approved': comment.comment_id in preapproved_responses,
            'verification_notes': [],
            'resolution': None,
            'author_justification': None,
        })
    package = {
        'schema_version': 1,
        'prepared_at': datetime.now(UTC).isoformat(),
        'project_metadata': {
            'manuscript_title': manifest.manuscript_title,
            'manuscript_id': manifest.manuscript_id,
            'journal': manifest.journal,
            'revision_round': manifest.revision_round,
        },
        'instructions': (
            'Draft author_response only from the supplied verified context. '
            'Preserve exact_comment and every traceability identifier exactly.'
        ),
        'entries': entries,
        'scientific_prose_generated_by_deterministic_code': False,
        'manuscript_modified': False,
    }
    write_json(root / 'working' / 'response_drafting_package.json', package)
    write_json(root / 'working' / 'response_entry_template.json', package)
    return package


def _strict_entries(
    project_root: str | Path,
    response_draft: str | Path | dict[str, Any],
) -> list[ResponseEntry]:
    sources = load_response_sources(project_root)
    payload = (
        read_json(response_draft)
        if isinstance(response_draft, (str, Path)) else response_draft
    )
    if not isinstance(payload, dict) or not isinstance(payload.get('entries'), list):
        raise ValueError('completed response draft must contain an entries list')
    comments = {item.comment_id: item for item in sources['comments']}
    raw_entries = payload['entries']
    ids = [
        str(item.get('comment_id')) for item in raw_entries if isinstance(item, dict)
    ]
    if len(ids) != len(raw_entries):
        raise ValueError('response entry is malformed')
    unknown = sorted(set(ids) - set(comments))
    missing = sorted(set(comments) - set(ids))
    if unknown:
        raise ValueError('unknown response comment IDs: ' + ', '.join(unknown))
    if missing:
        raise ValueError('missing response entries: ' + ', '.join(missing))
    if len(ids) != len(set(ids)):
        raise ValueError('duplicate response entries are not permitted')
    actions = {item.action_id: item for item in sources['actions']}
    action_ids = set(actions)
    changes = {item.change_id: item for item in sources['changes']}
    evidence = {str(item.get('evidence_id')): item for item in sources['evidence']}
    references = {str(item.get('reference_id')): item for item in sources['references']}
    preapproved_responses = approved_response_map(sources['root'])
    entries = []
    for raw in raw_entries:
        model_data = {
            key: value for key, value in raw.items()
            if key in ResponseEntry.model_fields
        }
        comment_id = str(model_data.get('comment_id', ''))
        approved_response = preapproved_responses.get(comment_id)
        if approved_response is not None:
            if model_data.get('author_response') != approved_response:
                raise ValueError(
                    f'{comment_id} response changed after researcher approval'
                )
            model_data['author_approved'] = True
        entry = ResponseEntry.model_validate(model_data)
        comment = comments[entry.comment_id]
        if entry.exact_comment != comment.original_comment:
            raise ValueError(f'{entry.comment_id} exact reviewer comment was altered')
        if set(entry.related_action_ids) - action_ids:
            raise ValueError(f'{entry.comment_id} references an unknown action')
        for action_id in entry.related_action_ids:
            if entry.comment_id not in actions[action_id].comment_ids:
                raise ValueError(
                    f'{entry.comment_id} references an action mapped to another comment'
                )
        for change_id in entry.related_change_ids:
            change = changes.get(change_id)
            if change is None or entry.comment_id not in change.comment_ids:
                raise ValueError(f'{entry.comment_id} references an invalid ChangeLog record')
            if change.verification_status != 'VERIFIED':
                raise ValueError(f'{entry.comment_id} references an unverified change')
        for evidence_id in entry.related_evidence_ids:
            if evidence_id not in evidence or str(evidence[evidence_id].get('status')) != 'VERIFIED':
                raise ValueError(f'{entry.comment_id} references missing or unverified evidence')
        for reference_id in entry.related_reference_ids:
            if reference_id not in references:
                raise ValueError(f'{entry.comment_id} references a missing bibliography record')
        entries.append(entry)
    return entries


def import_response_draft(
    project_root: str | Path,
    response_draft: str | Path | dict[str, Any],
) -> ResponsePackage:
    '''Import completed human/Codex prose; deterministic code adds no science.'''

    sources = load_response_sources(project_root)
    root = sources['root']
    manifest = load_project_manifest(root / 'config' / 'project_manifest.yaml')
    entries = _strict_entries(root, response_draft)
    grouped: dict[tuple[str, int | None], list[ResponseEntry]] = defaultdict(list)
    for entry in entries:
        grouped[(entry.reviewer_source.value, entry.reviewer_number)].append(entry)
    sections = []
    reviewer_numbers = sorted({
        int(number)
        for source, number in grouped
        if source == ReviewerSource.REVIEWER.value and number is not None
    })
    order = [
        (ReviewerSource.EDITOR.value, None),
        *[(ReviewerSource.REVIEWER.value, number) for number in reviewer_numbers],
        (ReviewerSource.GENERAL.value, None),
    ]
    for source, number in order:
        section_entries = sorted(
            grouped.pop((source, number), []), key=lambda item: item.sequence_number
        )
        if not section_entries:
            continue
        if source == ReviewerSource.REVIEWER.value:
            title = f'Reviewer {number}'
        elif source == ReviewerSource.EDITOR.value:
            title = 'Editor Comments'
        else:
            title = 'Shared and General Comments'
        sections.append(ReviewerResponseSection(
            section_id=f'SECTION-{len(sections) + 1:02d}',
            title=title,
            reviewer_source=source,
            reviewer_number=number,
            entries=section_entries,
        ))
    if grouped:
        raise ValueError('response draft contains an unsupported reviewer section')
    outputs = root / 'outputs'
    body = [
        'We appreciate the Editor and reviewers for their careful assessment of the manuscript.',
        (
            'The comments were considered individually, and the point-by-point '
            'responses below distinguish completed revisions from limitations, '
            'deferred work, and declined requests.'
        ),
        'Reviewer-specific revisions use the following deterministic legend: '
        + '; '.join(
            f'Reviewer {number} = '
            f'{highlight_for_reviewer_number(number).value.replace("_", " ").title()}'
            for number in reviewer_numbers
        )
        + ('; ' if reviewer_numbers else '')
        + 'shared or general revisions = Violet.',
    ]
    if (
        (outputs / 'Revised_Manuscript_Highlighted.docx').is_file()
        and (outputs / 'Revised_Manuscript_Clean.docx').is_file()
    ):
        body.append('Clean and highlighted revised manuscripts are included in the submission materials.')
    verified_sections = sorted({
        change.target_section for change in sources['changes']
        if change.verification_status == 'VERIFIED'
    })
    summary = [f'Applied and verified revisions are recorded in {name}.' for name in verified_sections]
    hashes = {
        name: sha256_file(path) for name, path in {
            'reviewer_comments': root / 'working' / 'reviewer_comments.json',
            'revision_plan': root / 'working' / 'revision_plan.json',
            'change_log': root / 'audit' / 'change_log.json',
        }.items() if path.is_file()
    }
    package = ResponsePackage(
        generated_at=datetime.now(UTC),
        manuscript_title=manifest.manuscript_title,
        manuscript_id=manifest.manuscript_id,
        journal=manifest.journal,
        revision_round=manifest.revision_round,
        cover_letter=EditorCoverLetter(body_paragraphs=body),
        summary_of_major_revisions=summary,
        sections=sections,
        closing_statement=(
            'We respectfully submit the revised manuscript and this point-by-point response for consideration.'
        ),
        package_status=ResponseStatus.DRAFTED,
        source_hashes=hashes,
        verification_metadata={'scientific_prose_generated_by_deterministic_code': False},
    )
    write_json(root / 'working' / 'response_package.json', package.model_dump(mode='json'))
    return package


class ResponseLetterService:
    def prepare(self, project_root: str | Path) -> dict[str, Any]:
        return build_response_drafting_package(project_root)

    def import_draft(
        self, project_root: str | Path, response_draft: str | Path | dict[str, Any]
    ) -> ResponsePackage:
        return import_response_draft(project_root, response_draft)
