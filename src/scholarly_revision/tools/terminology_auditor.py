'''Audit only configured, project-approved terminology variants.'''
from __future__ import annotations
import re
from scholarly_revision.models.scientific_audit import TerminologyAuditResult
from scholarly_revision.tools._audit_common import IssueFactory,section_name,section_titles,structure_from

def audit_terminology(source,terminology_rules=None,*,config:dict|None=None)->TerminologyAuditResult:
    structure=structure_from(source); titles=section_titles(structure); make=IssueFactory('TERMINOLOGY','TERM')
    rules=terminology_rules if terminology_rules is not None else (config or {}).get('terminology_rules',[])
    issues=[]; frequencies={}; locations={}
    for raw in rules:
        canonical=str(raw.get('canonical','')).strip()
        if not canonical: raise ValueError('terminology rule requires canonical')
        variants=[canonical,*[str(x) for x in raw.get('variants',[])]]
        counts={}; all_locations=[]
        for variant in dict.fromkeys(variants):
            count=0; found=[]
            pattern=re.compile(r'(?<!\w)'+re.escape(variant)+r'(?!\w)',0 if raw.get('case_sensitive') else re.I)
            for element in structure.elements:
                hits=len(pattern.findall(element.text))
                if hits: count+=hits; found.extend([element.element_id]*hits)
            counts[variant]=count; locations[f'{canonical}|{variant}']=found; all_locations.extend(found)
        frequencies[canonical]=counts
        used={term:count for term,count in counts.items() if count}
        if len(used)>1 or any(term!=canonical for term in used):
            issues.append(make('MINOR','Configured terminology variants are used inconsistently.',
                evidence=[f'canonical: {canonical}',f'frequencies: {used}'],
                manual=bool(raw.get('context_dependent',True))))
    return TerminologyAuditResult(issues=issues,term_frequencies=frequencies,locations=locations,
        checked_element_count=len(structure.elements),
        manual_review_required=any(i.manual_review_required for i in issues))

audit_terms=audit_terminology
