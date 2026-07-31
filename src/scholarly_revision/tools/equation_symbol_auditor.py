'''Audit equation numbering, references, symbol definitions, and consistency.'''
from __future__ import annotations
import re
from collections import Counter,defaultdict
from scholarly_revision.models.scientific_audit import EquationSymbolAuditResult
from scholarly_revision.tools._audit_common import IssueFactory,section_name,section_titles,structure_from

_LABEL=re.compile(r'\(\s*(\d+)\s*\)\s*$')
_REF=re.compile(r'\b(?:Eq(?:uation)?s?\.?)\s*\(?\s*(\d+)\s*\)?',re.I)
_SYMBOL=re.compile(r'(?<![\w])([A-Za-z\u03b1-\u03c9\u0391-\u03a9])(?=\s*(?:=|\+|-|\*|/|\^|\)))')
_DEFINITION=re.compile(r'\b(?:where\s+)?([A-Za-z\u03b1-\u03c9\u0391-\u03a9])\s+(?:is|denotes|represents|means)\s+([^.;]+)',re.I)
_ABBREV=re.compile(r'\b([A-Z]{2,6})\b')

def audit_equations_symbols(source,*,config:dict|None=None)->EquationSymbolAuditResult:
    structure=structure_from(source); titles=section_titles(structure); make=IssueFactory('EQUATION_SYMBOL','EQ')
    issues=[]; labels=[]; equation_elements=[]; references=[]; definitions=defaultdict(list); first_use={}
    complex_count=0
    for element in structure.elements:
        for match in _DEFINITION.finditer(element.text):
            definitions[match.group(1)].append((match.group(2).strip(),element))
        if element.element_type=='equation':
            equation_elements.append(element)
            label=_LABEL.search(element.text)
            if label: labels.append((int(label.group(1)),element))
            elif (config or {}).get('require_equation_numbers',True):
                issues.append(make('MAJOR','Equation has no detectable equation number.',
                    element=element,section=section_name(element,titles),manual=True))
            for symbol in _SYMBOL.findall(element.text):
                first_use.setdefault(symbol,element)
            if element.uncertain or not element.text.strip():
                complex_count+=1
                issues.append(make('INFORMATIONAL','Complex or uncertain equation requires manual mathematical review.',
                    element=element,resolution_required=False,manual=True))
        for match in _REF.finditer(element.text):
            references.append((int(match.group(1)),element,match.group(0)))
    counts=Counter(number for number,_ in labels)
    for number,count in counts.items():
        if count>1:
            issues.append(make('CRITICAL','Duplicate equation number detected.',
                evidence=[f'equation number: {number}',f'count: {count}']))
    sequence=[number for number,_ in labels]
    if sequence!=sorted(sequence):
        issues.append(make('MAJOR','Equation numbering is out of order.',evidence=[f'sequence: {sequence}']))
    if sequence:
        for missing in sorted(set(range(1,max(sequence)+1))-set(sequence)):
            issues.append(make('MAJOR','Equation numbering has a missing number.',evidence=[f'missing equation number: {missing}']))
    existing=set(sequence); referenced={n for n,_,_ in references}
    for number,element,exact in references:
        if number not in existing:
            issues.append(make('CRITICAL','In-text equation reference points to an absent equation.',
                element=element,section=section_name(element,titles),evidence=[f'exact reference: {exact}']))
    if (config or {}).get('require_equation_references',False):
        for number,element in labels:
            if number not in referenced:
                issues.append(make('MINOR','Numbered equation is never referenced in text.',
                    element=element,evidence=[f'equation number: {number}']))
    ignored=set((config or {}).get('defined_symbols',[]))|{'e','i'}
    for symbol,element in first_use.items():
        earlier=[item for item in definitions.get(symbol,[]) if item[1].order_index<element.order_index]
        if not earlier and symbol not in ignored:
            issues.append(make('MAJOR','Symbol is first used before a detectable definition.',
                element=element,section=section_name(element,titles),evidence=[f'symbol: {symbol}'],manual=True))
    for symbol,items in definitions.items():
        meanings={re.sub(r'\s+',' ',meaning.casefold()) for meaning,_ in items}
        if len(meanings)>1:
            issues.append(make('MAJOR','Conflicting definitions detected for the same symbol.',
                evidence=[f'symbol: {symbol}',f'definitions: {sorted(meanings)}'],manual=True))
    for element in equation_elements:
        for abbrev in _ABBREV.findall(element.text):
            if abbrev not in set((config or {}).get('defined_abbreviations',[])):
                issues.append(make('MINOR','Equation-associated abbreviation is undefined.',
                    element=element,evidence=[f'abbreviation: {abbrev}'],manual=True))
    return EquationSymbolAuditResult(issues=issues,equation_numbers=sequence,
        symbols_detected=sorted(first_use),checked_element_count=len(structure.elements),
        mathematical_correctness_checked=False,
        manual_review_required=any(i.manual_review_required for i in issues))

audit_equation_symbols=audit_equations_symbols
