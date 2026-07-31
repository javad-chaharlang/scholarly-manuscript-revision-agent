'''Audit figure/table captions and textual cross-references without renumbering.'''
from __future__ import annotations
import re
from collections import Counter,defaultdict
from scholarly_revision.models.scientific_audit import FigureTableAuditResult
from scholarly_revision.tools._audit_common import IssueFactory,section_name,section_titles,structure_from

_CAPTION=re.compile(r'^\s*(Figure|Fig\.|Table|Tbl\.)\s*(\d+)(?:\s*\(([a-z])\))?',re.I)
_REFERENCE=re.compile(r'\b(Figure|Fig\.|Table|Tbl\.)\s*(\d+)(?:\s*\(([a-z])\))?',re.I)

def audit_figures_tables(source,*,rendering_metadata:dict|None=None)->FigureTableAuditResult:
    structure=structure_from(source); titles=section_titles(structure); make=IssueFactory('FIGURE_TABLE','FIG')
    issues=[]; objects={'figure':defaultdict(list),'table':defaultdict(list)}
    references=[]; captions=[]
    for element in structure.elements:
        match=_CAPTION.match(element.text) if element.element_type in {'figure_caption','table_caption'} else None
        if match:
            kind='figure' if match.group(1).casefold().startswith('fig') else 'table'
            number=int(match.group(2)); sub=match.group(3)
            objects[kind][number].append((element,sub)); captions.append((kind,number,element))
        for match in _REFERENCE.finditer(element.text):
            if element.element_type in {'figure_caption','table_caption'} and match.start()==0: continue
            kind='figure' if match.group(1).casefold().startswith('fig') else 'table'
            references.append((kind,int(match.group(2)),match.group(3),element,match.group(0)))
    for kind,number_map in objects.items():
        sequence=sorted(number_map)
        counts={n:len(v) for n,v in number_map.items()}
        for number,count in counts.items():
            if count>1:
                issues.append(make('MAJOR',f'Duplicate {kind} caption number detected.',
                    evidence=[f'{kind} number: {number}',f'caption count: {count}']))
        if sequence:
            for missing in sorted(set(range(1,max(sequence)+1))-set(sequence)):
                issues.append(make('MAJOR',f'{kind.title()} numbering has a skipped number.',
                    evidence=[f'missing {kind} number: {missing}']))
            if sequence!=sorted(sequence):
                issues.append(make('MAJOR',f'{kind.title()} numbering is out of order.'))
    normalized=Counter(re.sub(r'\s+',' ',e.text.strip().casefold()) for _,_,e in captions)
    for text,count in normalized.items():
        if count>1:
            issues.append(make('MAJOR','Duplicate figure/table caption text detected.',
                evidence=[f'normalized caption: {text}',f'count: {count}']))
    referenced=defaultdict(list)
    for kind,number,sub,element,exact in references:
        referenced[(kind,number)].append(element.order_index)
        if number not in objects[kind]:
            issues.append(make('CRITICAL',f'Reference points to a non-existent {kind}.',
                element=element,section=section_name(element,titles),evidence=[f'exact reference: {exact}']))
        elif sub and all(obj_sub!=sub for _,obj_sub in objects[kind][number] if obj_sub):
            issues.append(make('MAJOR',f'{kind.title()} subpart reference conflicts with detected captions.',
                element=element,evidence=[f'exact reference: {exact}'],manual=True))
    for kind,number_map in objects.items():
        for number,items in number_map.items():
            key=(kind,number)
            if key not in referenced:
                issues.append(make('MINOR',f'{kind.title()} object is never referenced in text.',
                    element=items[0][0],evidence=[f'{kind} number: {number}'],manual=True))
            elif all(order>items[0][0].order_index for order in referenced[key]):
                issues.append(make('MINOR',f'All textual references to {kind} appear after the object.',
                    element=items[0][0],evidence=[f'{kind} number: {number}'],manual=True))
    for idx,element in enumerate(structure.elements):
        if element.element_type=='table' and (idx==0 or structure.elements[idx-1].element_type!='table_caption'):
            issues.append(make('MAJOR','Table caption is separated from its table or not detected.',
                element=element,manual=True))
    if rendering_metadata:
        for item in rendering_metadata.get('split_tables',[]):
            issues.append(make('MAJOR','Table is split across rendered pages.',
                evidence=[str(item)],manual=True))
    return FigureTableAuditResult(issues=issues,
        figures_detected=[f'Figure {n}' for n in sorted(objects['figure'])],
        tables_detected=[f'Table {n}' for n in sorted(objects['table'])],
        checked_element_count=len(structure.elements),
        visual_layout_checked=rendering_metadata is not None,
        manual_review_required=any(i.manual_review_required for i in issues))

audit_figure_table_consistency=audit_figures_tables
