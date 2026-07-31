'''Phase 6 deterministic scientific QA orchestration.'''
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from scholarly_revision.services.qa_report_service import update_qa_workbook,write_qa_reports
from scholarly_revision.services.scientific_qa_service import ScientificQAService,load_qa_config

@dataclass(frozen=True,slots=True)
class ScientificQAWorkflowResult:
    project_root:Path
    report:object
    report_paths:dict[str,Path]
    workbook_path:Path

def run_scientific_qa_workflow(*,project_root:str|Path,highlighted_manuscript:str|Path,
        clean_manuscript:str|Path,results_registry=None,reference_registry=None,
        config_path:str|Path|None=None)->ScientificQAWorkflowResult:
    root=Path(project_root).expanduser().resolve()
    required=(root/'outputs'/'Revision_Master.xlsx',)
    missing=[str(path) for path in required if not path.is_file()]
    if missing:raise FileNotFoundError('incomplete revision project: '+', '.join(missing))
    config=load_qa_config(config_path)
    change_log=root/'audit'/'change_log.json'
    run=ScientificQAService().run(highlighted_manuscript=highlighted_manuscript,
        clean_manuscript=clean_manuscript,results_registry=results_registry,
        reference_registry=reference_registry,config=config,
        change_log=change_log if change_log.is_file() else None)
    paths=write_qa_reports(root,run.report)
    workbook=update_qa_workbook(root/'outputs'/'Revision_Master.xlsx',run.report)
    return ScientificQAWorkflowResult(project_root=root,report=run.report,
        report_paths=paths,workbook_path=workbook)

run_workflow=run_scientific_qa_workflow
