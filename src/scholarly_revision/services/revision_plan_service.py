'''Generate deterministic, unapproved revision plans from completed assessments.'''

from __future__ import annotations

from datetime import UTC, datetime
from typing import Iterable

from scholarly_revision.models.enums import (
    ApprovalGateStatus,
    ApprovalState,
    ChangeType,
    CoverageStatus,
    RevisionStatus,
)
from scholarly_revision.models.gap_analysis import ActionProposal, GapAnalysisAssessment
from scholarly_revision.models.reviewer import RevisionAction


def _fallback_proposals(assessment: GapAnalysisAssessment) -> list[ActionProposal]:
    proposals: list[ActionProposal] = []
    for index, required_action in enumerate(assessment.required_actions):
        target_section = (
            assessment.target_sections[index]
            if index < len(assessment.target_sections)
            else (
                assessment.target_sections[0]
                if assessment.target_sections
                else 'UNSPECIFIED - MANUAL REVIEW REQUIRED'
            )
        )
        target_object = (
            assessment.target_objects[index]
            if index < len(assessment.target_objects)
            else None
        )
        questions = list(assessment.missing_elements)
        if not assessment.target_sections:
            questions.append('Target section must be selected by the author.')
        proposals.append(
            ActionProposal(
                linked_comment_ids=[assessment.comment_id, *assessment.shared_with_comments],
                change_type=ChangeType.GENERAL_CORRECTION,
                target_section=target_section,
                target_object=target_object,
                proposed_revision_summary=required_action,
                rationale=assessment.interpretation or 'Author-supplied required action.',
                evidence_requirements=[
                    item.description for item in assessment.manuscript_evidence
                    if item.status.value != 'VERIFIED'
                ],
                reference_requirements=assessment.required_references,
                experiment_requirements=assessment.required_experiments,
                statistical_requirements=assessment.required_statistics,
                unresolved_questions=questions,
            )
        )
    return proposals


def generate_revision_actions(
    assessments: Iterable[GapAnalysisAssessment],
    known_comment_ids: Iterable[str],
) -> list[RevisionAction]:
    '''Create stable ACT IDs without approving or claiming manuscript changes.'''

    known = set(known_comment_ids)
    candidates: list[tuple[str, ActionProposal]] = []
    grouped: dict[str, tuple[str, ActionProposal]] = {}
    for assessment in assessments:
        proposals = assessment.action_proposals or _fallback_proposals(assessment)
        for proposal in proposals:
            linked = list(dict.fromkeys(
                [assessment.comment_id, *proposal.linked_comment_ids,
                 *assessment.shared_with_comments]
            ))
            unknown = sorted(set(linked) - known)
            if unknown:
                raise ValueError(
                    'revision action references unknown comment IDs: '
                    + ', '.join(unknown)
                )
            normalized = proposal.model_copy(update={'linked_comment_ids': linked})
            if proposal.shared_action_key:
                prior = grouped.get(proposal.shared_action_key)
                if prior is None:
                    grouped[proposal.shared_action_key] = (assessment.comment_id, normalized)
                else:
                    _, existing = prior
                    comparable = (
                        'change_type', 'target_section', 'target_object',
                        'proposed_revision_summary', 'rationale',
                    )
                    if any(getattr(existing, key) != getattr(normalized, key) for key in comparable):
                        raise ValueError(
                            f'inconsistent shared action: {proposal.shared_action_key}'
                        )
                    merged = existing.model_copy(update={
                        'linked_comment_ids': list(dict.fromkeys(
                            [*existing.linked_comment_ids, *normalized.linked_comment_ids]
                        )),
                        'evidence_requirements': list(dict.fromkeys(
                            [*existing.evidence_requirements, *normalized.evidence_requirements]
                        )),
                        'reference_requirements': list(dict.fromkeys(
                            [*existing.reference_requirements, *normalized.reference_requirements]
                        )),
                        'experiment_requirements': list(dict.fromkeys(
                            [*existing.experiment_requirements, *normalized.experiment_requirements]
                        )),
                        'statistical_requirements': list(dict.fromkeys(
                            [*existing.statistical_requirements, *normalized.statistical_requirements]
                        )),
                        'unresolved_questions': list(dict.fromkeys(
                            [*existing.unresolved_questions, *normalized.unresolved_questions]
                        )),
                    })
                    grouped[proposal.shared_action_key] = (prior[0], merged)
            else:
                candidates.append((assessment.comment_id, normalized))
    candidates.extend(grouped.values())

    actions: list[RevisionAction] = []
    for number, (_, proposal) in enumerate(candidates, start=1):
        actions.append(
            RevisionAction(
                action_id=f'ACT-{number:04d}',
                comment_ids=proposal.linked_comment_ids,
                change_type=proposal.change_type,
                target_section=proposal.target_section,
                target_object=proposal.target_object,
                proposed_revision_summary=proposal.proposed_revision_summary,
                rationale=proposal.rationale,
                evidence_requirements=proposal.evidence_requirements,
                reference_requirements=proposal.reference_requirements,
                experiment_requirements=proposal.experiment_requirements,
                statistical_requirements=proposal.statistical_requirements,
                unresolved_questions=proposal.unresolved_questions,
                status=RevisionStatus.PLANNED,
                approval_state=ApprovalState.PENDING,
            )
        )
    return actions


def build_revision_plan(
    assessments: Iterable[GapAnalysisAssessment],
    known_comment_ids: Iterable[str],
    source_hash: str,
) -> dict[str, object]:
    actions = generate_revision_actions(assessments, known_comment_ids)
    return {
        'schema_version': 1,
        'generated_at': datetime.now(UTC).isoformat(),
        'source_gap_analysis_hash': source_hash,
        'manuscript_modified': False,
        'approval_gate_status': (
            ApprovalGateStatus.READY_FOR_REVIEW.value
            if actions else ApprovalGateStatus.NOT_READY.value
        ),
        'actions': [action.model_dump(mode='json') for action in actions],
    }


def plan_has_approval(plan: dict[str, object]) -> bool:
    for raw_action in plan.get('actions', []):
        if not isinstance(raw_action, dict):
            continue
        if raw_action.get('approval_state') == ApprovalState.APPROVED.value:
            return True
        if raw_action.get('approval_decision') in {'APPROVE', 'APPROVE_WITH_MODIFICATION'}:
            return True
    return plan.get('approval_gate_status') == ApprovalGateStatus.APPROVED.value
