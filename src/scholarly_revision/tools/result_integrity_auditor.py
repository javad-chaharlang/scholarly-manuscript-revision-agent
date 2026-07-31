'''Compare manuscript result claims with supplied local evidence records.'''
from __future__ import annotations
import re
from decimal import Decimal,InvalidOperation
from pathlib import Path
from scholarly_revision.models.scientific_audit import ResultIntegrityResult
from scholarly_revision.tools._audit_common import IssueFactory,load_records,section_name,section_titles,structure_from
from scholarly_revision.tools.numerical_consistency_auditor import extract_numerical_candidates

_RESULT_ID=re.compile(r'\bRES(?:ULT)?-\d{3,}\b',re.I)
_EXPERIMENT=re.compile(r'\b(?:we|the study)\s+(?:conducted|performed|ran)\s+(?:an?\s+)?experiment\b',re.I)
_STAT_CLAIM=re.compile(r'\b(?:statistically significant|significant difference|p\s*[<=>])\b',re.I)

def _decimal(value):
    try:return Decimal(str(value))
    except (InvalidOperation,ValueError,TypeError):return None

def audit_result_integrity(source,results_registry=None,*,config:dict|None=None)->ResultIntegrityResult:
    structure=structure_from(source); titles=section_titles(structure); make=IssueFactory('RESULT_INTEGRITY','RES')
    registry=load_records(results_registry); by_id={str(r.get('result_id')):r for r in registry}; issues=[]
    manuscript_ids=set(); matched_ids=set(); candidates=extract_numerical_candidates(structure,results_registry=registry,config=config)
    for element in structure.elements:
        ids={m.group(0).upper().replace('RESULT-','RES-') for m in _RESULT_ID.finditer(element.text)}
        manuscript_ids.update(ids)
        for result_id in ids:
            if result_id not in by_id:
                issues.append(make('CRITICAL','Manuscript result identifier has no registry entry.',
                    element=element,section=section_name(element,titles),evidence=[f'result ID: {result_id}']))
            else: matched_ids.add(result_id)
        if _EXPERIMENT.search(element.text) and not ids:
            issues.append(make('BLOCKER','Claimed experiment has no evidence record identifier.',
                element=element,section=section_name(element,titles),
                evidence=['experiment completion language detected'],manual=True))
        if _STAT_CLAIM.search(element.text):
            linked=[by_id[x] for x in ids if x in by_id]
            if not linked or any(not r.get('statistical_test_evidence_id') for r in linked):
                issues.append(make('BLOCKER','Statistical claim lacks linked test evidence.',
                    element=element,section=section_name(element,titles),
                    evidence=[f'linked result IDs: {sorted(ids)}'],manual=True))
    for candidate in candidates:
        if candidate.result_registry_link: matched_ids.add(candidate.result_registry_link)
        elif candidate.metric_name and (candidate.section or '').casefold() in {'abstract','results','discussion','conclusion'}:
            issues.append(make('MAJOR','Manuscript numerical result has no compatible registry entry.',
                evidence=[f'candidate: {candidate.candidate_id}',f'metric: {candidate.metric_name}'],manual=True))
    allowed={str(x).casefold() for x in (config or {}).get('approved_result_sections',[])}
    for result_id,record in by_id.items():
        status=str(record.get('result_status','')).upper(); evidence=str(record.get('evidence_status','')).upper()
        if result_id not in matched_ids:
            issues.append(make('INFORMATIONAL','Registry result is not used in the manuscript.',
                evidence=[f'result ID: {result_id}'],resolution_required=False))
        if status=='FINAL' and evidence!='VERIFIED':
            issues.append(make('BLOCKER','FINAL result does not have VERIFIED source evidence.',
                evidence=[f'result ID: {result_id}',f'evidence status: {evidence or "UNSPECIFIED"}']))
        if not record.get('source_file'):
            issues.append(make('BLOCKER' if status=='FINAL' else 'MAJOR','Result source file is missing.',
                evidence=[f'result ID: {result_id}']))
        elif not Path(str(record['source_file'])).exists() and bool((config or {}).get('verify_source_files',False)):
            issues.append(make('BLOCKER','Result source file cannot be found.',
                evidence=[f'result ID: {result_id}'],manual=True))
        if not record.get('source_cell_or_range'):
            issues.append(make('CRITICAL','Result source range is missing.',
                evidence=[f'result ID: {result_id}']))
        used={str(x).casefold() for x in record.get('used_in_sections',[])}
        if allowed and used-allowed:
            issues.append(make('CRITICAL','Result is used in a section outside the approved list.',
                evidence=[f'result ID: {result_id}',f'unapproved sections: {sorted(used-allowed)}']))
        if record.get('approved_value') is not None and _decimal(record.get('value'))!=_decimal(record.get('approved_value')):
            issues.append(make('BLOCKER','Result value changed after approval.',
                evidence=[f'result ID: {result_id}']))
    evidence_ids=[i.issue_id for i in issues if i.severity.value in {'BLOCKER','CRITICAL'} and
        any(word in i.description.casefold() for word in ('evidence','source','registry','experiment','statistical'))]
    return ResultIntegrityResult(issues=issues,manuscript_result_ids=sorted(manuscript_ids),
        registry_result_ids=sorted(by_id),evidence_integrity_issue_ids=evidence_ids,
        checked_element_count=len(structure.elements),
        manual_review_required=any(i.manual_review_required for i in issues))

audit_results=audit_result_integrity
