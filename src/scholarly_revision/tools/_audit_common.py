'''Shared deterministic helpers for Phase 6 auditors.'''
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Iterable
from scholarly_revision.models.scientific_audit import AuditIssue, issue
from scholarly_revision.tools.manuscript_structure_reader import (
    ManuscriptElement, ManuscriptStructure, read_manuscript_structure,
)

def structure_from(source: str|Path|ManuscriptStructure)->ManuscriptStructure:
    return source if isinstance(source, ManuscriptStructure) else read_manuscript_structure(source)

def load_records(source: str|Path|Iterable[Any]|None)->list[dict[str,Any]]:
    if source is None:
        return []
    if isinstance(source,(str,Path)):
        payload=json.loads(Path(source).read_text(encoding='utf-8'))
        if isinstance(payload,dict):
            for key in ('results','references','records'):
                if isinstance(payload.get(key),list):
                    payload=payload[key]; break
        if not isinstance(payload,list):
            raise ValueError('registry JSON must contain a list or a supported records key')
        source=payload
    result=[]
    for item in source:
        if hasattr(item,'model_dump'):
            item=item.model_dump(mode='json')
        if not isinstance(item,dict):
            raise ValueError('registry entries must be JSON objects')
        result.append(dict(item))
    return result

def section_titles(structure:ManuscriptStructure)->dict[str,str]:
    return {str(item['section_id']):str(item['title']) for item in structure.outline}

def section_name(element:ManuscriptElement,titles:dict[str,str])->str|None:
    return titles.get(element.section_id or '')

def context_class(element:ManuscriptElement)->str:
    if element.element_type=='table_cell_paragraph': return 'TABLE'
    if element.element_type=='figure_caption': return 'FIGURE_CAPTION'
    if element.element_type=='equation': return 'EQUATION'
    if element.element_type.startswith('reference_'): return 'BIBLIOGRAPHY'
    return 'BODY'

class IssueFactory:
    def __init__(self,category:str,prefix:str):
        self.category=category; self.prefix=prefix; self.number=0
    def __call__(self,severity:str,description:str,*,element:ManuscriptElement|None=None,
                 section:str|None=None,evidence:list[str]|None=None,
                 comments:list[str]|None=None,actions:list[str]|None=None,
                 manual:bool=False,resolution_required:bool=True)->AuditIssue:
        self.number+=1
        return issue(f'QA-{self.prefix}-{self.number:04d}',self.category,severity,description,
            element_id=element.element_id if element else None,section=section,
            evidence=evidence,related_comment_ids=comments,related_action_ids=actions,
            manual=manual,resolution_required=resolution_required)
