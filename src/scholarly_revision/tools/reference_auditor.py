'''Structural bibliography audit; no external bibliographic verification is implied.'''
from __future__ import annotations
import re
from collections import Counter
from scholarly_revision.models.reference import ReferenceRecord
from scholarly_revision.models.scientific_audit import BibliographyEntry,ReferenceAuditResult
from scholarly_revision.tools._audit_common import IssueFactory,load_records,section_name,section_titles,structure_from
from scholarly_revision.tools.manuscript_structure_reader import ManuscriptStructure

_NUMBER=re.compile(r'^\s*(?:\[(\d+)\]|(\d+)[.)])\s*(.*)$')
_YEAR=re.compile(r'\b(19\d{2}|20\d{2}|21\d{2})\b')
_DOI=re.compile(r'\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b',re.I)
_TEMP=re.compile(r'\b(?:TMP|TEMP)(?:ORARY)?[-_ ]?(?:REF)?[-_ ]?\d+\b|\[\s*T\d+\s*\]',re.I)

def _title_candidate(body:str,year:str|None)->str|None:
    parts=[part.strip(' .') for part in body.split('.') if part.strip()]
    candidates=[part for part in parts if len(part.split())>=3 and (not year or year not in part)]
    return candidates[0] if candidates else None

def extract_bibliography_entries(source)->list[BibliographyEntry]:
    structure=structure_from(source); result=[]
    for element in structure.elements:
        if element.element_type!='reference_entry': continue
        match=_NUMBER.match(element.text)
        number=int(match.group(1) or match.group(2)) if match else None
        body=match.group(3) if match else element.text
        year_match=_YEAR.search(body); year=year_match.group(1) if year_match else None
        parts=[p.strip() for p in body.split('.') if p.strip()]
        result.append(BibliographyEntry(number=number,exact_text=element.text,
            document_element_id=element.element_id,
            author_candidate=parts[0] if parts and len(parts[0].split())>=1 else None,
            title_candidate=_title_candidate(body,year),
            year_candidate=int(year) if year else None,
            source_candidate=parts[-1] if len(parts)>=3 else None,
            doi_like_strings=_DOI.findall(element.text),
            highlight_colors=list(element.highlight_colors)))
    return result

def audit_references(source,*,reference_registry=None)->ReferenceAuditResult:
    structure=structure_from(source); titles=section_titles(structure); make=IssueFactory('REFERENCE','REF')
    entries=extract_bibliography_entries(structure); issues=[]; numbers=[e.number for e in entries if e.number is not None]
    counts=Counter(numbers)
    for number,count in sorted(counts.items()):
        if count>1:
            issues.append(make('CRITICAL','Duplicate bibliography number detected.',
                evidence=[f'number: {number}',f'entry count: {count}']))
    if numbers:
        for number in sorted(set(range(1,max(numbers)+1))-set(numbers)):
            issues.append(make('MAJOR','Bibliography numbering sequence has a missing number.',
                evidence=[f'missing number: {number}']))
    title_map={}
    doi_map={}
    for entry in entries:
        if entry.number is None:
            issues.append(make('MAJOR','Bibliography entry has no detectable number.',
                evidence=[f'element: {entry.document_element_id}'],manual=True))
        missing=[]
        if not entry.author_candidate: missing.append('author')
        if not entry.title_candidate: missing.append('title')
        if not entry.year_candidate: missing.append('year')
        if not entry.source_candidate: missing.append('source')
        if missing:
            element=next(e for e in structure.elements if e.element_id==entry.document_element_id)
            issues.append(make('MAJOR','Reference entry has structurally missing bibliographic fields.',
                element=element,section=section_name(element,titles),
                evidence=['missing fields: '+', '.join(missing)],manual=True))
        if entry.title_candidate:
            normalized=re.sub(r'\W+',' ',entry.title_candidate.casefold()).strip()
            if normalized in title_map:
                issues.append(make('MAJOR','Duplicate reference title candidate detected.',
                    evidence=[f'entry elements: {title_map[normalized]}, {entry.document_element_id}'],manual=True))
            title_map[normalized]=entry.document_element_id
        for doi in entry.doi_like_strings:
            normalized=doi.rstrip('.,;').casefold()
            if normalized in doi_map:
                issues.append(make('MAJOR','Duplicate DOI-like string detected structurally.',
                    evidence=[f'DOI-like string: {doi}',f'entry elements: {doi_map[normalized]}, {entry.document_element_id}'],manual=True))
            doi_map[normalized]=entry.document_element_id
            prefixed=bool(re.search(r'(?:doi:\s*|https?://(?:dx\.)?doi\.org/)\s*'+re.escape(doi),entry.exact_text,re.I))
            trailing=doi.endswith(('.',',',';'))
            if doi!=doi.strip() or prefixed or trailing:
                issues.append(make('MINOR','DOI-like string has a formatting issue.',
                    evidence=[f'entry element: {entry.document_element_id}'],manual=True))
    registry=load_records(reference_registry)
    registry_by_number={r.get('final_number'):r for r in registry if r.get('final_number')}
    for entry in entries:
        raw=registry_by_number.get(entry.number)
        if raw:
            comments=raw.get('requested_by_comment_ids') or []
            expected=raw.get('highlight')
            if comments and not entry.highlight_colors:
                issues.append(make('MAJOR','Reviewer-added reference is missing an expected highlight.',
                    evidence=[f'reference number: {entry.number}'],comments=list(comments)))
            if entry.highlight_colors and not comments:
                issues.append(make('MAJOR','Highlighted reference has no reviewer mapping.',
                    evidence=[f'reference number: {entry.number}'],manual=True))
            if expected and entry.highlight_colors and expected not in entry.highlight_colors:
                issues.append(make('MAJOR','Reference highlight conflicts with its reviewer mapping.',
                    evidence=[f'reference number: {entry.number}',f'expected: {expected}',f'actual: {entry.highlight_colors}'],comments=list(comments)))
    for element in structure.elements:
        for match in _TEMP.finditer(element.text):
            issues.append(make('CRITICAL','Temporary reference number remains in manuscript content.',
                element=element,section=section_name(element,titles),evidence=[f'exact artifact: {match.group(0)}']))
    return ReferenceAuditResult(issues=issues,entries=entries,total_reference_count=len(entries),
        numbering_sequence=numbers,checked_element_count=len(structure.elements),
        bibliographic_verification_performed=False,
        manual_review_required=any(i.manual_review_required for i in issues))

audit_bibliography=audit_references
