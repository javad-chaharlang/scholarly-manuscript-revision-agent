from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from scholarly_revision.models.enums import (
    ApprovalState,
    ChangeType,
    RevisionStatus,
)
from scholarly_revision.models.reviewer import ReviewerComment, RevisionAction
from scholarly_revision.services.gap_analysis_service import read_json, write_json
from scholarly_revision.services.comment_approval_service import (
    prepare_comment_approval,
    record_comment_approval_decision,
)
from scholarly_revision.tools.workbook_builder import update_revision_workbook
from scholarly_revision.workflows.gap_analysis_workflow import prepare_gap_analysis
from scholarly_revision.workflows.intake_workflow import IntakeRequest, run_intake_workflow
from scholarly_revision.workflows.revision_execution_workflow import (
    import_completed_revision_drafts,
    import_completed_text_decisions,
    prepare_revision_drafts,
)


TESTS = Path(__file__).parent
REVIEWERS = TESTS / 'fixtures' / 'synthetic_reviewer_comments.docx'
MANUSCRIPT = TESTS / 'fixtures' / 'synthetic_manuscript.docx'


def make_phase5_project(tmp_path: Path, *, action_count: int = 10) -> Path:
    root = run_intake_workflow(IntakeRequest(
        workspace_root=tmp_path / 'private-workspaces',
        project_name='Anonymous Phase Five',
        manuscript_id='SYNTHETIC-PHASE-5',
        reviewer_file=REVIEWERS,
        manuscript_file=MANUSCRIPT,
    )).workspace.root
    prepare_gap_analysis(root, MANUSCRIPT)
    comments = [
        ReviewerComment.model_validate(item)
        for item in read_json(root / 'working' / 'reviewer_comments.json')
    ]
    specifications = [
        ('R1-C01', ChangeType.REWRITE, 'Introduction', 'PAR-0006', 'Replace synthetic introduction.'),
        ('R2-C01', ChangeType.ADDITION, 'Related Work', 'PAR-0008', 'Insert synthetic context.'),
        ('R1-C02', ChangeType.REWRITE, 'Proposed Method', 'SEC-004', 'Replace synthetic heading.'),
        ('R2-C02', ChangeType.FIGURE_REVISION, 'Experiments', 'FIG-001', 'Replace synthetic figure caption.'),
        ('R1-C01', ChangeType.TABLE_REVISION, 'Experiments', 'PAR-0022', 'Replace synthetic table cell.'),
        (['R1-C01', 'R2-C01'], ChangeType.GENERAL_CORRECTION, 'Limitations', 'PAR-0040', 'Apply shared synthetic clarification.'),
        ('GEN-C01', ChangeType.REWRITE, 'Abstract', 'PAR-0004', 'Synthetic draft for rejection.'),
        ('GEN-C02', ChangeType.REWRITE, 'Proposed Method', 'PAR-0010', 'Synthetic draft for deferral.'),
        ('ED-C01', ChangeType.REWRITE, 'Experiments', 'PAR-0017', 'Synthetic evidence-dependent draft.'),
        ('R1-C02', ChangeType.REWRITE, 'Results', 'PAR-0027', 'Synthetic rewrite-request draft.'),
    ][:action_count]
    actions: list[RevisionAction] = []
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    for number, (raw_comments, change_type, section, target, summary) in enumerate(
        specifications, start=1
    ):
        comment_ids = raw_comments if isinstance(raw_comments, list) else [raw_comments]
        actions.append(RevisionAction(
            action_id=f'ACT-{number:04d}',
            comment_ids=comment_ids,
            change_type=change_type,
            target_section=section,
            target_object=target,
            proposed_revision_summary=summary,
            rationale='Anonymous synthetic rationale approved for drafting.',
            status=RevisionStatus.PLANNED,
            approval_state=ApprovalState.APPROVED,
            approval_decision='APPROVE',
            decision_timestamp=timestamp,
            decision_maker='anonymous-author',
        ))
    plan = {
        'schema_version': 1,
        'generated_at': timestamp.isoformat(),
        'source_gap_analysis_hash': '0' * 64,
        'manuscript_modified': False,
        'approval_gate_status': 'APPROVED',
        'actions': [action.model_dump(mode='json') for action in actions],
    }
    write_json(root / 'working' / 'revision_plan.json', plan)
    update_revision_workbook(
        root / 'outputs' / 'Revision_Master.xlsx',
        comments,
        [],
        actions,
        'APPROVED',
    )
    return root


def complete_and_import_drafts(root: Path) -> Path:
    prepare_revision_drafts(root)
    payload = read_json(root / 'working' / 'revision_draft_template.json')
    texts = {
        'DRAFT-0001': 'This anonymous introduction now states a clearer fictional context.',
        'DRAFT-0002': 'This inserted sentence supplies additional anonymous context.',
        'DRAFT-0003': 'Synthetic Method',
        'DRAFT-0004': 'Figure 1. Revised anonymous placeholder workflow.',
        'DRAFT-0005': 'Revised placeholder alpha',
        'DRAFT-0006': 'The fixture limitations are clarified for both anonymous reviewers.',
        'DRAFT-0007': 'A draft that the anonymous author will reject.',
        'DRAFT-0008': 'A draft that the anonymous author will defer.',
        'DRAFT-0009': 'A draft that requires an evidence decision.',
        'DRAFT-0010': 'A draft that the anonymous author will request to rewrite.',
    }
    for entry in payload['drafts']:
        draft = entry['draft']
        draft['proposed_text'] = texts[draft['draft_id']]
        draft['draft_status'] = 'DRAFTED'
    completed = root / 'working' / 'completed_revision_drafts.json'
    write_json(completed, payload)
    import_completed_revision_drafts(root, completed)
    return completed


def decide_all_drafts(root: Path) -> Path:
    drafts = read_json(root / 'working' / 'revision_drafts.json')
    decisions = []
    for entry in drafts['drafts']:
        draft = entry['draft']
        draft_id = draft['draft_id']
        record = {
            'draft_id': draft_id,
            'decision_maker': 'anonymous-author',
            'decision_timestamp': '2030-01-02T00:00:00Z',
            'approved_text': None,
            'author_modified_text': None,
            'author_note': None,
            'evidence_request': None,
            'rewrite_instruction': None,
            'unresolved_questions': [],
        }
        if draft_id in {'DRAFT-0001', 'DRAFT-0003', 'DRAFT-0004', 'DRAFT-0005', 'DRAFT-0006'}:
            record['decision'] = 'APPROVE_TEXT'
            record['approved_text'] = draft['proposed_text']
        elif draft_id == 'DRAFT-0002':
            record['decision'] = 'APPROVE_TEXT_WITH_MODIFICATION'
            record['author_modified_text'] = (
                'This author-modified insertion supplies exact anonymous context.'
            )
            record['approved_text'] = record['author_modified_text']
        elif draft_id == 'DRAFT-0007':
            record['decision'] = 'REJECT_TEXT'
            record['author_note'] = 'The anonymous author rejects this exact wording.'
        elif draft_id == 'DRAFT-0008':
            record['decision'] = 'DEFER_TEXT'
        elif draft_id == 'DRAFT-0009':
            record['decision'] = 'NEED_MORE_EVIDENCE'
            record['evidence_request'] = 'Provide a verified anonymous evidence record.'
        else:
            record['decision'] = 'REQUEST_REWRITE'
            record['rewrite_instruction'] = 'Use narrower anonymous language.'
        decisions.append(record)
    decision_file = root / 'working' / 'completed_text_decisions.json'
    write_json(decision_file, {'schema_version': 1, 'decisions': decisions})
    import_completed_text_decisions(root, decision_file)
    return decision_file


def setup_approved_project(tmp_path: Path) -> Path:
    root = make_phase5_project(tmp_path)
    complete_and_import_drafts(root)
    decide_all_drafts(root)
    prepare_comment_approval(root)
    approval = read_json(root / 'working' / 'comment_approval_working.json')
    for record in approval['records']:
        approved_ids = [
            item['draft_id'] for item in record.get('proposed_changes', [])
            if item.get('text_approval_state') == 'APPROVED'
            and not item.get('manual_handling_required')
        ]
        record_comment_approval_decision(
            root,
            comment_id=record['comment_id'],
            proposed_response=(
                f"Thank you for the {record['comment_id']} comment. "
                'The approved revision scope has been reviewed by the author.'
            ),
            decision='APPROVE_PACKAGE',
            decision_maker='anonymous-author',
            approved_draft_ids=approved_ids,
        )
    return root
