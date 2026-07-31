'''Verify repository highlight policy and highlighted/clean equivalence.'''
from __future__ import annotations
import json
from pathlib import Path
from docx import Document
from scholarly_revision.models.scientific_audit import HighlightAuditResult
from scholarly_revision.tools._audit_common import IssueFactory,load_records
from scholarly_revision.tools.docx_clean_copy import validate_text_equivalence
from scholarly_revision.tools.docx_highlight_manager import (
    HIGHLIGHT_INDEX,SYSTEM_STYLE_PREFIX,_system_marker,iter_document_paragraphs,
)

def _runs(path):
    document=Document(Path(path)); records=[]; author=0; invalid=[]
    for paragraph in iter_document_paragraphs(document):
        for run in paragraph.runs:
            marker=_system_marker(run)
            if marker:
                color,change_id=marker
                records.append((change_id,color.value,run.font.highlight_color==HIGHLIGHT_INDEX[color],run.text))
            elif run.style is not None and run.style.name.startswith(SYSTEM_STYLE_PREFIX):
                invalid.append(run.style.name)
            elif run.font.highlight_color is not None:
                author+=1
    return records,author,invalid

def audit_highlights(highlighted_manuscript,clean_manuscript,*,change_log=None,reference_registry=None)->HighlightAuditResult:
    make=IssueFactory('HIGHLIGHT','HL'); issues=[]
    highlighted,author_h,invalid_h=_runs(highlighted_manuscript)
    clean,author_c,invalid_c=_runs(clean_manuscript)
    for style in invalid_h+invalid_c:
        issues.append(make('MAJOR','Unrecognized system highlight color or marker.',
            evidence=[f'style marker: {style}']))
    if isinstance(change_log,(str,Path)):
        raw=json.loads(Path(change_log).read_text(encoding='utf-8'))
        changes=[dict(x) for x in raw.get('changes',[])] if isinstance(raw,dict) else [dict(x) for x in raw]
    else:
        changes=load_records(change_log)
    expected={}
    for record in changes:
        change_id=str(record.get('change_id',''))
        comments=[str(x) for x in record.get('comment_ids',[])]
        sources={x.split('-',1)[0] for x in comments}
        color='YELLOW' if sources=={'R1'} else ('BRIGHT_GREEN' if sources=={'R2'} else 'VIOLET')
        expected[change_id]=(color,comments,str(record.get('action_id','')))
    seen=set()
    for change_id,color,actual_matches,_ in highlighted:
        seen.add(change_id)
        if not actual_matches:
            issues.append(make('MAJOR','System marker and visible highlight color do not match.',
                evidence=[f'change ID: {change_id}',f'marker color: {color}']))
        if change_id not in expected:
            issues.append(make('MAJOR','Unchanged or unmapped text is highlighted by the system.',
                evidence=[f'change ID: {change_id}'],manual=True))
        elif expected[change_id][0]!=color:
            exp,comments,action=expected[change_id]
            issues.append(make('CRITICAL','Reviewer change uses the incorrect repository highlight color.',
                evidence=[f'change ID: {change_id}',f'expected: {exp}',f'actual: {color}'],
                comments=comments,actions=[action] if action else []))
    for change_id,(color,comments,action) in expected.items():
        if change_id not in seen:
            issues.append(make('MAJOR','Expected reviewer highlight is missing.',
                evidence=[f'change ID: {change_id}',f'expected: {color}'],comments=comments,
                actions=[action] if action else []))
    if clean:
        issues.append(make('BLOCKER','Clean manuscript retains system-generated reviewer highlights.',
            evidence=[f'system highlight count: {len(clean)}']))
    equivalent=validate_text_equivalence(highlighted_manuscript,clean_manuscript)
    if not equivalent:
        issues.append(make('BLOCKER','Highlighted and clean manuscripts do not contain equivalent text.'))
    if author_c<author_h:
        issues.append(make('MAJOR','Unrelated author highlighting may not have been preserved in the clean manuscript.',
            evidence=[f'highlighted author runs: {author_h}',f'clean author runs: {author_c}'],manual=True))
    registry=load_records(reference_registry)
    for record in registry:
        if record.get('highlight') and not record.get('requested_by_comment_ids'):
            issues.append(make('MAJOR','Highlighted reference has no reviewer mapping.',
                evidence=[f'reference ID: {record.get("reference_id")}'],manual=True))
    return HighlightAuditResult(issues=issues,highlighted_system_run_count=len(highlighted),
        clean_system_run_count=len(clean),text_equivalent=equivalent,
        unrelated_author_highlights_preserved=author_c>=author_h,
        checked_element_count=len(highlighted)+len(clean),
        manual_review_required=any(i.manual_review_required for i in issues))

audit_highlight_policy=audit_highlights
