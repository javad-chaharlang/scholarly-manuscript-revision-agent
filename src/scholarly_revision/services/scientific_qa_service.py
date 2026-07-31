'''Run every deterministic Phase 6 auditor without manuscript mutation or network access.'''
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml
from scholarly_revision.services.project_workspace import sha256_file
from scholarly_revision.services.qa_report_service import aggregate_report
from scholarly_revision.tools.citation_auditor import audit_citations
from scholarly_revision.tools.reference_auditor import audit_references
from scholarly_revision.tools.numerical_consistency_auditor import audit_numerical_consistency
from scholarly_revision.tools.result_integrity_auditor import audit_result_integrity
from scholarly_revision.tools.figure_table_auditor import audit_figures_tables
from scholarly_revision.tools.equation_symbol_auditor import audit_equations_symbols
from scholarly_revision.tools.terminology_auditor import audit_terminology
from scholarly_revision.tools.highlight_auditor import audit_highlights
from scholarly_revision.tools.front_matter_auditor import audit_front_matter

@dataclass(frozen=True,slots=True)
class ScientificQARun:
    report:Any
    results:tuple[Any,...]
    source_hashes:dict[str,str]

def load_qa_config(path:str|Path|None)->dict[str,Any]:
    if path is None:return {}
    source=Path(path)
    if not source.is_file():raise FileNotFoundError(f'QA config not found: {source}')
    payload=yaml.safe_load(source.read_text(encoding='utf-8'))
    if payload is None:return {}
    if not isinstance(payload,dict):raise ValueError('QA config must contain a YAML mapping')
    return payload

class ScientificQAService:
    def run(self,*,highlighted_manuscript:str|Path,clean_manuscript:str|Path,
            results_registry=None,reference_registry=None,config:dict[str,Any]|None=None,
            change_log=None)->ScientificQARun:
        highlighted=Path(highlighted_manuscript).expanduser().resolve()
        clean=Path(clean_manuscript).expanduser().resolve()
        for path,label in ((highlighted,'highlighted manuscript'),(clean,'clean manuscript')):
            if path.suffix.lower()!='.docx':raise ValueError(f'{label} must be DOCX')
            if not path.is_file():raise FileNotFoundError(f'{label} not found: {path}')
        cfg=config or {}
        references=audit_references(highlighted,reference_registry=reference_registry)
        citations=audit_citations(highlighted,bibliography_count=references.total_reference_count)
        results=(
            citations,references,
            audit_numerical_consistency(highlighted,results_registry=results_registry,config=cfg.get('numerical',{})),
            audit_result_integrity(highlighted,results_registry,config=cfg.get('results',{})),
            audit_figures_tables(highlighted,rendering_metadata=cfg.get('rendering_metadata')),
            audit_equations_symbols(highlighted,config=cfg.get('equations',{})),
            audit_terminology(highlighted,config=cfg),
            audit_highlights(highlighted,clean,change_log=change_log,reference_registry=reference_registry),
            audit_front_matter(highlighted,config=cfg.get('front_matter',{})),
        )
        hashes={'highlighted_manuscript':sha256_file(highlighted),'clean_manuscript':sha256_file(clean)}
        if isinstance(results_registry,(str,Path)):hashes['results_registry']=sha256_file(results_registry)
        if isinstance(reference_registry,(str,Path)):hashes['reference_registry']=sha256_file(reference_registry)
        report=aggregate_report(results,hashes)
        return ScientificQARun(report=report,results=results,source_hashes=hashes)

def run_scientific_qa(**kwargs)->ScientificQARun:
    return ScientificQAService().run(**kwargs)
