'''Extract and compare numerical claims without changing scientific values.'''
from __future__ import annotations
import re
from collections import defaultdict
from decimal import Decimal,InvalidOperation
from scholarly_revision.models.scientific_audit import NumericalCandidate,NumericalConsistencyResult
from scholarly_revision.tools._audit_common import IssueFactory,load_records,section_name,section_titles,structure_from

_MEAN=re.compile(r'(?P<mean>[+-]?\d+(?:\.\d+)?)\s*[±\u00b1]\s*(?P<disp>\d+(?:\.\d+)?)\s*(?P<unit>%|[A-Za-z\u00b5\u03bc/][\w\u00b5\u03bc/^.-]*)?')
_PVALUE=re.compile(r'\bp\s*(?P<op>[<=>])\s*(?P<value>\d*\.?\d+(?:[eE][+-]?\d+)?)',re.I)
_NUMBER=re.compile(r'(?<![\w.-])(?P<value>[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*(?P<unit>%|[A-Za-z\u00b5\u03bc/][\w\u00b5\u03bc/^.-]*)?')
_METRIC=re.compile(r'(?P<metric>[A-Za-z][A-Za-z0-9 _/-]{1,48}?)\s*(?:=|:|was|is|of)\s*$',re.I)
_IMPROVEMENT=re.compile(r'from\s+(\d+(?:\.\d+)?)\s*(%)?\s+to\s+(\d+(?:\.\d+)?)\s*(%)?.{0,50}?(\d+(?:\.\d+)?)\s*%\s*(?:improvement|increase)',re.I)

def _decimal(value)->Decimal|None:
    try:return Decimal(str(value))
    except (InvalidOperation,ValueError,TypeError):return None

def _metric_before(text:str,start:int)->str|None:
    prefix=text[max(0,start-70):start]
    exact=re.search(r'([A-Za-z_][A-Za-z0-9_-]*)\s*=\s*$',prefix)
    if exact:return exact.group(1).casefold()
    match=_METRIC.search(prefix)
    if match:return ' '.join(match.group('metric').split()).casefold()
    words=re.findall(r'[A-Za-z][A-Za-z0-9_-]*',prefix)
    return words[-1].casefold() if words else None

def extract_numerical_candidates(source,*,results_registry=None,config:dict|None=None)->list[NumericalCandidate]:
    structure=structure_from(source); titles=section_titles(structure); registry=load_records(results_registry)
    candidates=[]; counter=0
    allowed={s.casefold() for s in (config or {}).get('sections',[]) }
    for element in structure.elements:
        section=section_name(element,titles)
        if allowed and (section or '').casefold() not in allowed: continue
        occupied=[]
        for pattern,kind in ((_MEAN,'MEAN_SD'),(_PVALUE,'P_VALUE')):
            for match in pattern.finditer(element.text):
                counter+=1; occupied.append(match.span())
                raw=match.group('mean') if kind=='MEAN_SD' else match.group('value')
                unit=match.groupdict().get('unit')
                metric='p-value' if kind=='P_VALUE' else _metric_before(element.text,match.start())
                link=next((str(r.get('result_id')) for r in registry
                    if metric and str(r.get('metric_name','')).casefold()==metric and _decimal(r.get('value'))==_decimal(raw)),None)
                candidates.append(NumericalCandidate(candidate_id=f'NUM-{counter:04d}',metric_name=metric,
                    value=raw,unit=unit,section=section,source_element=element.element_id,
                    surrounding_context=element.text,dataset=None,configuration=None,
                    result_registry_link=link,value_kind=kind))
        for match in _NUMBER.finditer(element.text):
            if any(a<=match.start()<b for a,b in occupied):continue
            counter+=1; raw=match.group('value'); metric=_metric_before(element.text,match.start())
            link=next((str(r.get('result_id')) for r in registry
                if metric and str(r.get('metric_name','')).casefold()==metric and _decimal(r.get('value'))==_decimal(raw)),None)
            candidates.append(NumericalCandidate(candidate_id=f'NUM-{counter:04d}',metric_name=metric,
                value=raw,unit=match.group('unit'),section=section,source_element=element.element_id,
                surrounding_context=element.text,result_registry_link=link,
                value_kind='PERCENTAGE' if match.group('unit')=='%' else ('SCIENTIFIC_NOTATION' if 'e' in raw.lower() else 'NUMBER')))
    return candidates

def audit_numerical_consistency(source,*,results_registry=None,config:dict|None=None,response_mapping=None)->NumericalConsistencyResult:
    structure=structure_from(source); make=IssueFactory('NUMERICAL_CONSISTENCY','NUM')
    registry=load_records(results_registry); candidates=extract_numerical_candidates(structure,results_registry=registry,config=config)
    issues=[]; groups=defaultdict(list)
    by_id={str(r.get('result_id')):r for r in registry}
    for candidate in candidates:
        if candidate.metric_name:
            key=(candidate.metric_name.casefold(),candidate.dataset,candidate.configuration,candidate.unit)
            groups[key].append(candidate)
        if candidate.result_registry_link:
            record=by_id.get(candidate.result_registry_link,{})
            status=str(record.get('result_status','')).upper()
            if (candidate.section or '').casefold() in {'abstract','conclusion'} and status in {'DRAFT','UNVERIFIED',''}:
                issues.append(make('BLOCKER','Draft or unverified value is used in a final-claim section.',
                    evidence=[f'candidate: {candidate.candidate_id}',f'result: {candidate.result_registry_link}',f'status: {status or "UNSPECIFIED"}']))
        if candidate.value_kind=='P_VALUE':
            linked=by_id.get(candidate.result_registry_link or '',{})
            if not linked.get('statistical_test_evidence_id'):
                issues.append(make('CRITICAL','P-value has no linked statistical-test evidence.',
                    evidence=[f'candidate: {candidate.candidate_id}'],manual=True))
    for key,items in groups.items():
        values={_decimal(item.value) for item in items}
        values.discard(None)
        if len(values)>1:
            issues.append(make('MAJOR','Compatible metric context contains different numerical values.',
                evidence=[f'metric/configuration key: {key}',f'candidates: {[i.candidate_id for i in items]}'],manual=True))
        units={i.unit for i in items if i.unit}
        if len(units)>1:
            issues.append(make('MAJOR','Compatible metric context uses inconsistent units.',
                evidence=[f'metric/configuration key: {key}',f'units: {sorted(units)}'],manual=True))
    for element in structure.elements:
        for match in _IMPROVEMENT.finditer(element.text):
            old,new,claimed=map(Decimal,(match.group(1),match.group(3),match.group(5)))
            if old!=0:
                calculated=(new-old)/old*100
                tolerance=Decimal(str((config or {}).get('percentage_tolerance',0.1)))
                if abs(calculated-claimed)>tolerance:
                    issues.append(make('MAJOR','Stated percentage improvement does not match the displayed source values.',
                        element=element,evidence=[f'claimed: {claimed}%',f'mathematical calculation: {calculated.normalize()}%'],manual=True))
    required={str(x).casefold() for x in (config or {}).get('dispersion_required_metrics',[])}
    for candidate in candidates:
        if candidate.metric_name and candidate.metric_name.casefold() in required and candidate.value_kind!='MEAN_SD':
            issues.append(make('MAJOR','Configured mean metric is reported without required dispersion.',
                evidence=[f'candidate: {candidate.candidate_id}',f'metric: {candidate.metric_name}'],manual=True))
    return NumericalConsistencyResult(issues=issues,candidates=candidates,
        checked_element_count=len(structure.elements),
        mathematical_checks_performed=['percentage arithmetic'],
        scientific_verification_performed=False,
        manual_review_required=any(i.manual_review_required for i in issues))

audit_numbers=audit_numerical_consistency
