'''Deterministic numeric citation auditing without renumbering or inference.'''
from __future__ import annotations
import re
from collections import Counter
from pathlib import Path
from zipfile import ZipFile
from scholarly_revision.models.scientific_audit import CitationAuditResult,CitationOccurrence
from scholarly_revision.tools._audit_common import IssueFactory,context_class,section_name,section_titles,structure_from
from scholarly_revision.tools.manuscript_structure_reader import ManuscriptStructure

_BRACKET=re.compile(r'\[[^\[\]\r\n]{1,80}\]')
_NUMERIC_BODY=re.compile(r'^\s*\d+(?:\s*(?:,|;|[-\u2012\u2013\u2014])\s*\d+)*\s*$')
_RANGE=re.compile(r'^\s*(\d+)\s*([-\u2012\u2013\u2014])\s*(\d+)\s*$')
_SPLIT=re.compile(r'\s*[,;]\s*')

def parse_citation_group(exact_text:str)->list[int]:
    '''Normalize one valid numeric group; raise for malformed or descending ranges.'''
    if not (exact_text.startswith('[') and exact_text.endswith(']')):
        raise ValueError('citation group must retain square brackets')
    body=exact_text[1:-1]
    if not _NUMERIC_BODY.fullmatch(body):
        raise ValueError('citation group contains a non-numeric or malformed artifact')
    numbers=[]
    for token in _SPLIT.split(body):
        match=_RANGE.fullmatch(token)
        if match:
            start,end=int(match.group(1)),int(match.group(3))
            if start>end: raise ValueError('descending citation range')
            numbers.extend(range(start,end+1))
        elif token.strip().isdigit():
            numbers.append(int(token.strip()))
        else:
            raise ValueError('malformed citation range')
    return numbers

def _endnote_elements(path:Path)->set[str]:
    try:
        with ZipFile(path) as archive:
            xml=archive.read('word/document.xml').decode('utf-8','replace')
    except Exception:
        return set()
    return {'PRESERVE'} if re.search(r'EndNote|ADDIN EN\.CITE|EN.CITE',xml,re.I) else set()

def audit_citations(source:str|Path|ManuscriptStructure,*,bibliography_count:int|None=None)->CitationAuditResult:
    structure=structure_from(source); titles=section_titles(structure); make=IssueFactory('CITATION','CIT')
    occurrences=[]; issues=[]; cited=[]; reference_numbers=[]
    reference_boundary=(structure.reference_section_boundary or {}).get('order_index')
    endnote_present=_endnote_elements(Path(source)) if not isinstance(source,ManuscriptStructure) else set()
    for element in structure.elements:
        if element.element_type=='reference_entry':
            match=re.match(r'^\s*\[?(\d+)\]?\s*[.)]?',element.text)
            if match: reference_numbers.append(int(match.group(1)))
        for match in _BRACKET.finditer(element.text):
            exact=match.group(0); numbers=[]; error=None
            try: numbers=parse_citation_group(exact)
            except ValueError as exc: error=str(exc)
            citation_like=bool(numbers) or bool(re.search(r'\d',exact))
            if not citation_like and context_class(element)=='EQUATION':
                continue
            occurrence=CitationOccurrence(exact_text=exact,normalized_numbers=numbers,
                document_element_id=element.element_id,section=section_name(element,titles),
                structural_context=context_class(element),order_index=element.order_index,
                endnote_field_code=bool(endnote_present))
            occurrences.append(occurrence)
            if error:
                severity='MAJOR' if re.search(r'\d',exact) else 'MINOR'
                issues.append(make(severity,error.capitalize()+'.',element=element,
                    section=occurrence.section,evidence=[f'exact citation: {exact}'],manual=True))
                continue
            counts=Counter(numbers)
            duplicate=sorted(n for n,c in counts.items() if c>1)
            if duplicate:
                issues.append(make('MAJOR','Duplicate citation numbers occur in one citation group.',
                    element=element,section=occurrence.section,
                    evidence=[f'exact citation: {exact}',f'duplicates: {duplicate}']))
            if occurrence.structural_context!='BIBLIOGRAPHY':
                cited.extend(numbers)
            if reference_boundary is not None and element.order_index>reference_boundary and context_class(element)!='BIBLIOGRAPHY':
                issues.append(make('MAJOR','A citation appears after the References section.',
                    element=element,section=occurrence.section,evidence=[f'exact citation: {exact}']))
    if endnote_present:
        issues.append(make('MAJOR','EndNote field codes are present and must be preserved for manual review.',
            evidence=['field code detected in DOCX package'],manual=True))
    bibliography_count=bibliography_count if bibliography_count is not None else len(reference_numbers)
    cited_set=sorted(set(cited))
    if bibliography_count:
        for number in sorted(n for n in cited_set if n>bibliography_count):
            issues.append(make('CRITICAL','Citation number exceeds the detected bibliography count.',
                evidence=[f'citation number: {number}',f'bibliography count: {bibliography_count}']))
        for number in sorted(set(range(1,bibliography_count+1))-set(cited_set)):
            issues.append(make('MAJOR','Bibliography entry is never cited in manuscript text.',
                evidence=[f'reference number: {number}']))
    if reference_numbers:
        expected=set(range(1,max(reference_numbers)+1))
        for number in sorted(expected-set(reference_numbers)):
            issues.append(make('MAJOR','Final reference numbering contains a gap.',
                evidence=[f'missing reference number: {number}']))
    return CitationAuditResult(issues=issues,occurrences=occurrences,
        cited_reference_numbers=cited_set,bibliography_count=bibliography_count,
        checked_element_count=len(structure.elements),
        manual_review_required=any(item.manual_review_required for item in issues))

audit_numeric_citations=audit_citations
