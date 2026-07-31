'''List revision actions or record one explicit human approval decision.'''

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / 'src'
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from scholarly_revision.models.enums import ApprovalDecision  # noqa: E402
from scholarly_revision.models.gap_analysis import GapAnalysisAssessment  # noqa: E402
from scholarly_revision.models.reviewer import ReviewerComment, RevisionAction  # noqa: E402
from scholarly_revision.services.approval_service import (  # noqa: E402
    decision_template,
    record_decision,
)
from scholarly_revision.services.gap_analysis_service import read_json, write_json  # noqa: E402
from scholarly_revision.tools.workbook_builder import update_revision_workbook  # noqa: E402


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Review the Phase 4 revision plan.')
    parser.add_argument('--project-root', required=True, type=Path)
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--export-template', type=Path)
    parser.add_argument('--action-id')
    parser.add_argument('--decision', choices=[item.value for item in ApprovalDecision])
    parser.add_argument('--decision-maker')
    parser.add_argument('--author-note')
    parser.add_argument('--modified-action-text')
    parser.add_argument('--evidence-request')
    parser.add_argument('--unresolved-question', action='append', default=[])
    return parser


def _sync_workbook(root: Path, plan: dict[str, object]) -> None:
    comments = [
        ReviewerComment.model_validate(item)
        for item in read_json(root / 'working' / 'reviewer_comments.json')
    ]
    imported = read_json(root / 'working' / 'gap_analysis_imported.json')
    assessments = [
        GapAnalysisAssessment.model_validate(item)
        for item in imported['assessments']
    ]
    actions = [
        RevisionAction.model_validate(item) for item in plan['actions']
    ]
    update_revision_workbook(
        root / 'outputs' / 'Revision_Master.xlsx',
        comments,
        assessments,
        actions,
        str(plan['approval_gate_status']),
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    arguments = parser.parse_args(argv)
    root = arguments.project_root.expanduser().resolve()
    plan_path = root / 'working' / 'revision_plan.json'
    try:
        plan = read_json(plan_path)
        if not isinstance(plan, dict):
            raise ValueError('revision_plan.json must contain an object')
        if arguments.export_template:
            write_json(arguments.export_template, decision_template(plan))
            print(f'Decision template: {arguments.export_template}')
        if arguments.list or (
            not arguments.export_template and not arguments.action_id
        ):
            for raw in plan.get('actions', []):
                print(
                    f"{raw['action_id']} | {raw['approval_state']} | "
                    f"{raw['target_section']} | {raw.get('proposed_revision_summary') or ''}"
                )
            print(f"Approval gate: {plan.get('approval_gate_status')}")
        if arguments.action_id:
            if not arguments.decision or not arguments.decision_maker:
                parser.error(
                    '--action-id requires --decision and --decision-maker'
                )
            plan = record_decision(
                plan,
                action_id=arguments.action_id,
                decision=arguments.decision,
                decision_maker=arguments.decision_maker,
                author_note=arguments.author_note,
                modified_action_text=arguments.modified_action_text,
                evidence_request=arguments.evidence_request,
                unresolved_questions=arguments.unresolved_question,
            )
            write_json(plan_path, plan)
            _sync_workbook(root, plan)
            print(f'Decision recorded for: {arguments.action_id}')
            print(f"Approval gate: {plan['approval_gate_status']}")
    except SystemExit:
        raise
    except Exception as exc:
        print(f'Revision-plan review failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
