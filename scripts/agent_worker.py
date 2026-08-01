'''Run one already-approved queued task in a separate local process.'''
from __future__ import annotations
import argparse
from scholarly_revision.services.agent_worker_service import AgentWorkerService

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--project-root', required=True)
    parser.add_argument('--task-id', required=True)
    args = parser.parse_args()
    return AgentWorkerService(args.project_root).run(args.task_id)

if __name__ == '__main__':
    raise SystemExit(main())
