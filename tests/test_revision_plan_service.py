from scholarly_revision.models.enums import HighlightColor
from scholarly_revision.models.gap_analysis import GapAnalysisAssessment
from scholarly_revision.services.revision_plan_service import build_revision_plan, generate_revision_actions


def assessment(proposals: list[dict]) -> GapAnalysisAssessment:
    return GapAnalysisAssessment(comment_id='R1-C01', original_comment='Synthetic.',
        coverage_status='NOT_ADDRESSED', interpretation='Author supplied.',
        required_actions=['Plan action.'], target_sections=['Results'],
        action_proposals=proposals)


def test_action_generation_and_initial_state() -> None:
    proposal = {'linked_comment_ids': ['R1-C01'], 'change_type': 'ADDITION',
        'target_section': 'Results', 'proposed_revision_summary': 'Add context.',
        'rationale': 'Respond to request.'}
    actions = generate_revision_actions([assessment([proposal, dict(proposal,
        proposed_revision_summary='Add limitation.')])], ['R1-C01'])
    assert [item.action_id for item in actions] == ['ACT-0001', 'ACT-0002']
    assert all(item.approval_state.value == 'PENDING' for item in actions)
    assert all(item.status.value == 'PLANNED' for item in actions)


def test_shared_action_highlight_and_plan_gate() -> None:
    proposal = {'shared_action_key': 'shared', 'linked_comment_ids': ['R1-C01', 'R2-C01'],
        'target_section': 'Limitations', 'proposed_revision_summary': 'Shared change.',
        'rationale': 'Two comments share one action.'}
    actions = generate_revision_actions([assessment([proposal])], ['R1-C01', 'R2-C01'])
    assert actions[0].highlight is HighlightColor.VIOLET
    plan = build_revision_plan([assessment([proposal])], ['R1-C01', 'R2-C01'], '0' * 64)
    assert plan['manuscript_modified'] is False
    assert plan['approval_gate_status'] == 'READY_FOR_REVIEW'
