from app.db.models import (
    Agent,
    AuditLog,
    Bottleneck,
    Employee,
    Meeting,
    MeetingItem,
    SlaRecord,
    SystemMetric,
    ToolConnection,
    User,
    Workflow,
    WorkflowStep,
)


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


def serialize_workflow_step(step: WorkflowStep) -> dict:
    failure_scenario = None
    if step.can_fail and step.failure_name and step.failure_detection:
        failure_scenario = {
            "name": step.failure_name,
            "detection": step.failure_detection,
            "recovery": step.failure_recovery or [],
        }

    return {
        "id": step.id,
        "name": step.name,
        "agent": step.agent,
        "status": step.status,
        "time": step.time_label,
        "detail": step.detail,
        "reasoning": step.reasoning,
        "confidence": step.confidence,
        "duration": step.duration_ms,
        "alternatives": step.alternatives or [],
        "canFail": step.can_fail,
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
        "startDate": employee.start_date_label,
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
