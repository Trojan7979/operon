from app.db.models import (
    Agent,
    AgentRun,
    AgentTask,
    AuditLog,
    Bottleneck,
    Conversation,
    ConversationMessage,
    Employee,
    Meeting,
    MeetingItem,
    SlaRecord,
    SystemMetric,
    ToolInvocation,
    ToolConnection,
    User,
    Workflow,
    WorkflowStep,
)
from app.services.employees import serialize_employee_start_date


DEMO_STEP_ENRICHMENTS = {
    ("wf-901", 1): {
        "reasoning": "Inbound intake classified the request as a procurement event, extracted the vendor name and value, and created a workflow envelope before any human review was needed.",
        "confidence": 98.6,
        "duration": 1400,
        "alternatives": ["Hold for manual procurement desk triage"],
    },
    ("wf-901", 2): {
        "reasoning": "Data Fetcher cross-checked the vendor profile against connected finance systems and confirmed the supplier already exists with valid master data and payment terms.",
        "confidence": 97.9,
        "duration": 1800,
        "alternatives": ["Create a new vendor onboarding packet"],
    },
    ("wf-901", 3): {
        "reasoning": "Shield Verifier detected the missing W-9 signature, paused progression, and triggered an automated remediation path instead of escalating immediately.",
        "confidence": 94.2,
        "duration": 2300,
        "alternatives": ["Escalate to procurement operations", "Block the workflow until the vendor replies"],
        "canFail": True,
        "failureScenario": {
            "name": "Missing Compliance Artifact",
            "detection": "The vendor W-9 arrived without a valid signature block, so the compliance gate failed.",
            "recovery": [
                {"action": "Logged the compliance defect and paused execution", "agent": "Shield Verifier"},
                {"action": "Drafted and sent a corrected signature request to the vendor", "agent": "Action Exec Alpha"},
                {"action": "Monitored the inbox and attached the signed document once received", "agent": "Data Fetcher v4"},
                {"action": "Re-ran compliance validation and reopened the approval path", "agent": "Shield Verifier"},
            ],
        },
    },
    ("wf-901", 4): {
        "reasoning": "The orchestrator mapped the spend amount to the VP approval threshold and pushed a Slack approval with a fallback email in parallel to reduce SLA risk.",
        "confidence": 96.4,
        "duration": 2100,
        "alternatives": ["Route to finance director", "Queue the request for next-day batch approval"],
    },
    ("wf-901", 5): {
        "reasoning": "Action Exec Alpha is holding the payment handoff until approval clears so the ERP update and payment scheduling can execute atomically.",
        "confidence": 95.1,
        "duration": 1700,
        "alternatives": ["Create the PO now and schedule payment later"],
    },
    ("wf-902", 1): {
        "reasoning": "The onboarding trigger came from a signed offer artifact, so the workflow started with verified employee identity and start-date context.",
        "confidence": 99.4,
        "duration": 1200,
        "alternatives": ["Wait for HR manual confirmation"],
    },
    ("wf-902", 2): {
        "reasoning": "Provisioning APIs were executed in parallel for workspace, messaging, and engineering tools with rollback protection for partial failures.",
        "confidence": 97.8,
        "duration": 2400,
        "alternatives": ["Route account setup to IT service desk"],
    },
    ("wf-902", 3): {
        "reasoning": "Once provisioning completed, the system packaged the welcome email with first-day instructions and tool access confirmation to avoid duplicate HR outreach.",
        "confidence": 98.7,
        "duration": 1300,
        "alternatives": ["Send a generic onboarding template"],
    },
    ("wf-902", 4): {
        "reasoning": "The orchestrator matched the role to the premium engineering equipment bundle and opened the IT request before the employee start date to protect readiness.",
        "confidence": 96.1,
        "duration": 1600,
        "alternatives": ["Issue the standard employee hardware kit"],
    },
    ("wf-903", 1): {
        "reasoning": "Action Exec Alpha generated the draft from the approved commercial template so legal could review a clean baseline instead of a manually assembled contract.",
        "confidence": 97.5,
        "duration": 1500,
        "alternatives": ["Start from last year's redline version"],
    },
    ("wf-903", 2): {
        "reasoning": "MeetIntel compared the current redlines against prior negotiation patterns and surfaced the clauses most likely to trigger legal review delays.",
        "confidence": 93.8,
        "duration": 2200,
        "alternatives": ["Send the full document straight to legal without triage"],
    },
    ("wf-903", 3): {
        "reasoning": "The contract exceeded the legal review SLA, so the orchestrator escalated rather than continuing to wait on an unowned queue.",
        "confidence": 91.6,
        "duration": 1800,
        "alternatives": ["Hold the workflow for another review cycle", "Escalate directly to executive approval"],
    },
}


def build_failure_scenario(step: WorkflowStep) -> dict | None:
    if step.can_fail and step.failure_name and step.failure_detection:
        return {
            "name": step.failure_name,
            "detection": step.failure_detection,
            "recovery": step.failure_recovery or [],
        }

    enrichment = DEMO_STEP_ENRICHMENTS.get((step.workflow_id, step.position), {})
    return enrichment.get("failureScenario")


def serialize_metric(metric: SystemMetric) -> dict:
    return {
        "activeWorkflows": metric.active_workflows,
        "tasksAutomated": metric.tasks_automated,
        "humanEscalations": metric.human_escalations,
        "selfCorrections": metric.self_corrections,
        "uptime": metric.uptime,
        "autonomyRate": metric.autonomy_rate,
    }


def serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "avatar": user.avatar,
        "status": user.status,
        "department": user.department,
        "permissions": user.permissions,
    }


def serialize_agent(agent: Agent) -> dict:
    return {
        "id": agent.id,
        "name": agent.name,
        "role": agent.role,
        "status": agent.status,
        "successRate": agent.success_rate,
        "currentTask": agent.current_task,
        "avatar": agent.avatar,
    }


def serialize_agent_task(task: AgentTask) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "assignedAgentId": task.assigned_agent_id,
        "workflowId": task.workflow_id,
        "conversationId": task.conversation_id,
        "createdAt": task.created_at.isoformat(),
        "updatedAt": task.updated_at.isoformat(),
    }


def serialize_agent_metrics(
    agent: Agent,
    *,
    total_runs: int,
    completed_runs: int,
    failed_runs: int,
    active_tasks: int,
    average_duration_ms: int,
    tool_invocations: int,
) -> dict:
    success_rate = round((completed_runs / total_runs) * 100, 1) if total_runs else agent.success_rate
    return {
        "agentId": agent.id,
        "totalRuns": total_runs,
        "completedRuns": completed_runs,
        "failedRuns": failed_runs,
        "activeTasks": active_tasks,
        "averageDurationMs": average_duration_ms,
        "toolInvocations": tool_invocations,
        "successRate": success_rate,
    }


def serialize_agent_history_entry(
    *,
    entry_id: str,
    entry_type: str,
    status: str,
    summary: str,
    created_at,
) -> dict:
    return {
        "id": entry_id,
        "entryType": entry_type,
        "status": status,
        "summary": summary,
        "createdAt": created_at.isoformat(),
    }


def serialize_workflow_step(step: WorkflowStep) -> dict:
    enrichment = DEMO_STEP_ENRICHMENTS.get((step.workflow_id, step.position), {})
    failure_scenario = build_failure_scenario(step)
    confidence = step.confidence if step.confidence is not None else enrichment.get("confidence")
    duration = step.duration_ms if step.duration_ms is not None else enrichment.get("duration", 1600)
    reasoning = step.reasoning or enrichment.get("reasoning") or step.detail
    alternatives = step.alternatives or enrichment.get("alternatives") or []
    can_fail = step.can_fail or bool(failure_scenario) or bool(enrichment.get("canFail"))

    return {
        "id": step.id,
        "name": step.name,
        "agent": step.agent,
        "status": step.status,
        "time": step.time_label,
        "detail": step.detail,
        "reasoning": reasoning,
        "confidence": confidence,
        "duration": duration,
        "alternatives": alternatives,
        "canFail": can_fail,
        "failureScenario": failure_scenario,
    }


def serialize_workflow(workflow: Workflow) -> dict:
    return {
        "id": workflow.id,
        "type": workflow.workflow_type,
        "name": workflow.name,
        "status": workflow.status,
        "health": workflow.health,
        "progress": workflow.progress,
        "currentStep": workflow.current_step,
        "assignedAgent": workflow.assigned_agent,
        "prediction": workflow.prediction,
        "autoAction": workflow.auto_action,
        "steps": [serialize_workflow_step(step) for step in workflow.steps],
    }


def serialize_audit_log(log: AuditLog) -> dict:
    return {
        "id": log.id,
        "time": log.time_label,
        "type": log.log_type,
        "agent": log.agent,
        "message": log.message,
    }


def serialize_conversation_message(message: ConversationMessage) -> dict:
    return {
        "id": message.id,
        "role": message.role,
        "senderName": message.sender_name,
        "agentId": message.agent_id,
        "content": message.content,
        "createdAt": message.created_at.isoformat(),
    }


def serialize_conversation(conversation: Conversation, messages: list[ConversationMessage] | None = None) -> dict:
    return {
        "id": conversation.id,
        "title": conversation.title,
        "status": conversation.status,
        "ownerUserId": conversation.owner_user_id,
        "primaryAgentId": conversation.primary_agent_id,
        "workflowId": conversation.workflow_id,
        "lastMessageAt": conversation.last_message_at.isoformat(),
        "createdAt": conversation.created_at.isoformat(),
        "messages": [serialize_conversation_message(message) for message in messages or []],
    }


def serialize_meeting_item(item: MeetingItem) -> dict:
    return {
        "type": item.item_type,
        "text": item.text,
        "owner": item.owner,
        "status": item.status,
        "deadline": item.deadline_label,
        "daysLeft": item.days_left,
    }


def serialize_meeting(meeting: Meeting) -> dict:
    return {
        "id": meeting.id,
        "title": meeting.title,
        "provider": meeting.provider,
        "date": meeting.date_label,
        "time": meeting.time_label,
        "duration": meeting.duration,
        "attendees": meeting.attendees,
        "status": meeting.status,
        "agentJoined": meeting.agent_joined,
        "agentName": meeting.agent_name,
        "gcalEventId": meeting.gcal_event_id,
        "meetLink": meeting.meet_link,
        "htmlLink": meeting.html_link,
        "transcript": [
            {"time": line.time_label, "speaker": line.speaker, "text": line.text}
            for line in meeting.transcript_lines
        ],
        "extracted": [serialize_meeting_item(item) for item in meeting.extracted_items],
    }



def serialize_employee(employee: Employee) -> dict:
    return {
        "id": employee.id,
        "name": employee.name,
        "role": employee.role,
        "department": employee.department,
        "email": employee.email,
        "phone": employee.phone,
        "location": employee.location,
        "startDate": serialize_employee_start_date(employee.start_date),
        "status": employee.status,
        "progress": employee.progress,
        "avatar": employee.avatar,
        "photo": employee.photo_url,
    }


def serialize_sla_record(record: SlaRecord) -> dict:
    return {
        "id": record.id,
        "name": record.name,
        "type": record.workflow_type,
        "slaHours": record.sla_hours,
        "elapsedHours": record.elapsed_hours,
        "status": record.status,
        "currentStep": record.current_step,
        "agent": record.agent,
        "prediction": record.prediction,
        "health": record.health,
        "autoAction": record.auto_action,
    }


def serialize_bottleneck(bottleneck: Bottleneck) -> dict:
    return {
        "area": bottleneck.area,
        "avgDelay": bottleneck.avg_delay,
        "frequency": bottleneck.frequency,
        "risk": bottleneck.risk,
        "suggestion": bottleneck.suggestion,
    }


def serialize_tool(tool: ToolConnection) -> dict:
    return {
        "id": tool.id,
        "name": tool.name,
        "toolType": tool.tool_type,
        "description": tool.description,
        "status": tool.status,
        "mcpServer": tool.mcp_server,
        "capabilities": tool.capabilities,
    }


def serialize_tool_invocation(invocation: ToolInvocation) -> dict:
    return {
        "id": invocation.id,
        "toolName": invocation.tool_name,
        "action": invocation.action,
        "status": invocation.status,
        "summary": invocation.summary,
        "payload": invocation.payload,
        "createdAt": invocation.created_at.isoformat(),
    }
