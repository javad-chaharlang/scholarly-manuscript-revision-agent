'''Create, inspect, approve, queue, or execute a local Codex task.'''
from __future__ import annotations
import argparse
import json
from scholarly_revision.models.agent_run import AgentAuthorDecision
from scholarly_revision.models.agent_task import AgentTaskType, TransmissionDecision
from scholarly_revision.services.agent_task_service import AgentTaskService
from scholarly_revision.services.agent_worker_service import AgentWorkerService

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--project-root', required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    create = sub.add_parser('create')
    create.add_argument('--task-type', choices=[item.value for item in AgentTaskType], required=True)
    create.add_argument('--purpose', required=True)
    create.add_argument('--actor', required=True)
    create.add_argument('--comment-id', action='append', default=[])
    create.add_argument('--action-id', action='append', default=[])
    create.add_argument('--element-id', action='append', default=[])
    for name in ('prepare', 'approve-transmission', 'queue', 'run', 'cancel'):
        command = sub.add_parser(name)
        command.add_argument('--task-id', required=True)
        if name in {'approve-transmission', 'queue', 'cancel'}:
            command.add_argument('--actor', required=True)
    decide = sub.add_parser('decide-output')
    decide.add_argument('--task-id', required=True)
    decide.add_argument('--actor', required=True)
    decide.add_argument('--decision', choices=[item.value for item in AgentAuthorDecision], required=True)
    retry = sub.add_parser('retry')
    retry.add_argument('--task-id', required=True)
    retry.add_argument('--actor', required=True)
    retry.add_argument('--instruction', required=True)
    args = parser.parse_args()
    service = AgentTaskService(args.project_root)
    if args.command == 'create':
        value = service.create_task(
            task_type=args.task_type, purpose=args.purpose, created_by=args.actor,
            related_comment_ids=args.comment_id, related_action_ids=args.action_id,
            source_element_ids=args.element_id,
        )
    elif args.command == 'prepare':
        value = service.prepare_context(args.task_id)
    elif args.command == 'approve-transmission':
        value = service.transmission_decision(
            args.task_id, TransmissionDecision.APPROVE_TRANSMISSION, actor=args.actor,
        )
    elif args.command == 'queue':
        value = service.queue(args.task_id, actor=args.actor)
    elif args.command == 'run':
        return AgentWorkerService(args.project_root).run(args.task_id)
    elif args.command == 'cancel':
        value = service.cancel(args.task_id, actor=args.actor)
    elif args.command == 'retry':
        value = service.retry(
            args.task_id, instruction=args.instruction, actor=args.actor,
        )
    else:
        value = service.decide_output(args.task_id, args.decision, actor=args.actor)
    payload = value.model_dump(mode='json') if hasattr(value, 'model_dump') else value
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
