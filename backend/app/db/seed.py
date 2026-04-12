from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.db.models import (
    Agent,
    AgentHandoff,
    AgentRun,
    AgentTask,
    AuthSession,
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
    TranscriptLine,
    User,
    Workflow,
    WorkflowStep,
)


ROLE_TEMPLATES = {
    "Super Admin": [
        "dashboard",
        "simulator",
        "onboarding",
        "workflows",
        "agents",
        "collab",
        "meetings",
        "sla",
        "chat",
        "audit",
        "rbac",
    ],
    "VP Engineering": [
        "dashboard",
        "simulator",
        "workflows",
        "agents",
        "collab",
        "meetings",
        "sla",
        "chat",
        "audit",
    ],
    "Product Manager": ["dashboard", "workflows", "meetings", "chat"],
    "UX Designer": ["dashboard", "meetings", "chat"],
    "Backend Lead": [
        "dashboard",
        "simulator",
        "workflows",
        "agents",
        "collab",
        "sla",
        "chat",
        "audit",
    ],
    "HR Manager": ["dashboard", "onboarding", "meetings", "chat"],
    "Auditor": ["dashboard", "audit"],
}


async def seed_database(session: AsyncSession) -> None:
    existing_user = await session.scalar(select(User.id).limit(1))
    if existing_user:
        await seed_phase1_extensions(session)
        return

    session.add(
        SystemMetric(
            id=1,
            active_workflows=142,
            tasks_automated=15430,
            human_escalations=12,
            self_corrections=843,
            uptime="99.99%",
            autonomy_rate="99.92%",
        )
    )

    users = [
        ("u-1", "Admin User", "admin@nexuscore.ai", "admin123", "Super Admin", "AU", "IT"),
        ("u-2", "Sarah Chen", "sarah@nexuscore.ai", "sarah123", "VP Engineering", "SC", "Engineering"),
        ("u-3", "James Rodriguez", "james@nexuscore.ai", "james123", "Product Manager", "JR", "Product"),
        ("u-4", "Rupam Jana", "rupam@nexuscore.ai", "rupam123", "Backend Lead", "RJ", "Engineering"),
        ("u-5", "Cassandra Vale", "cassandra@nexuscore.ai", "cassandra123", "UX Designer", "CV", "Design"),
        ("u-6", "Maria Lopez", "maria@nexuscore.ai", "maria123", "HR Manager", "ML", "HR"),
        ("u-7", "David Brown", "david@nexuscore.ai", "david123", "Auditor", "DB", "Compliance"),
    ]
    for user_id, name, email, password, role, avatar, department in users:
        session.add(
            User(
                id=user_id,
                name=name,
                email=email,
                password_hash=get_password_hash(password),
                role=role,
                avatar=avatar,
                status="active" if role != "Auditor" else "inactive",
                department=department,
                permissions=ROLE_TEMPLATES[role],
            )
        )

    agents = [
        Agent(
            id="ag-orchestrator",
            name="Nexus Orchestrator",
            role="Workflow Manager",
            status="active",
            success_rate=99.8,
            current_task="Routing Procurement Approval #4492",
            avatar="Cpu",
        ),
        Agent(
            id="ag-intel",
            name="MeetIntel Core",
            role="Meeting Intelligence",
            status="processing",
            success_rate=98.5,
            current_task="Extracting Action Items from Q3 Sync",
            avatar="BrainCircuit",
        ),
        Agent(
            id="ag-retrieval",
            name="Data Fetcher v4",
            role="Context Retrieval",
            status="idle",
            success_rate=99.9,
            current_task="Awaiting next query",
            avatar="Database",
        ),
        Agent(
            id="ag-executor",
            name="Action Exec Alpha",
            role="Execution Engine",
            status="active",
            success_rate=97.4,
            current_task="Updating Salesforce Records",
            avatar="Zap",
        ),
        Agent(
            id="ag-verifier",
            name="Shield Verifier",
            role="Quality Assurance",
            status="self-correcting",
            success_rate=99.1,
            current_task="Re-validating missing invoice signatures",
            avatar="ShieldCheck",
        ),
    ]
    session.add_all(agents)

    workflows = [
        Workflow(
            id="wf-901",
            workflow_type="Procure-to-Pay",
            name="Acme Corp Software License",
            status="in-progress",
            health=100,
            progress=75,
            current_step="Manager Approval",
            assigned_agent="Nexus Orchestrator",
            prediction="Expected to close inside SLA after VP approval.",
        ),
        Workflow(
            id="wf-902",
            workflow_type="Employee Onboarding",
            name="Taniya Kundu (Engineering)",
            status="completed",
            health=100,
            progress=100,
            current_step="Hardware Procurement",
            assigned_agent="Nexus Orchestrator",
            prediction="Completed autonomously.",
        ),
        Workflow(
            id="wf-903",
            workflow_type="Contract Lifecycle",
            name="Globex Enterprise Renewal",
            status="warning",
            health=65,
            progress=40,
            current_step="Legal Review",
            assigned_agent="Human (Legal)",
            prediction="SLA breach likely within 2 hours without intervention.",
            auto_action="Escalated to Legal Lead",
        ),
    ]
    session.add_all(workflows)

    workflow_steps = [
        ("wf-901", 1, "Request Received", "System", "completed", "10:00 AM", None),
        ("wf-901", 2, "Vendor Verification", "Data Fetcher v4", "completed", "10:02 AM", None),
        (
            "wf-901",
            3,
            "Compliance Check",
            "Shield Verifier",
            "self-corrected",
            "10:05 AM",
            "Missing W-9. Automatically generated request to vendor.",
        ),
        (
            "wf-901",
            4,
            "Manager Approval",
            "Nexus Orchestrator",
            "in-progress",
            "10:15 AM",
            "Sent Slack ping to VP of Engineering",
        ),
        ("wf-901", 5, "Payment Execution", "Action Exec Alpha", "pending", "-", None),
        ("wf-902", 1, "Offer Accepted", "System", "completed", "Yesterday", None),
        ("wf-902", 2, "Accounts Provisioning", "Action Exec Alpha", "completed", "09:00 AM", None),
        ("wf-902", 3, "Welcome Email Sent", "System", "completed", "09:05 AM", None),
        (
            "wf-902",
            4,
            "Hardware Procurement",
            "Nexus Orchestrator",
            "completed",
            "09:10 AM",
            "Assigned to IT queue",
        ),
        ("wf-903", 1, "Draft Generation", "Action Exec Alpha", "completed", "08:00 AM", None),
        ("wf-903", 2, "Redlining Analysis", "MeetIntel Core", "completed", "08:45 AM", None),
        (
            "wf-903",
            3,
            "Legal Review",
            "Human (Legal)",
            "escalated",
            "System Warning",
            "SLA risk: stalled for 48h. Agent escalated.",
        ),
    ]
    for workflow_id, position, name, agent, status, time_label, detail in workflow_steps:
        session.add(
            WorkflowStep(
                workflow_id=workflow_id,
                position=position,
                name=name,
                agent=agent,
                status=status,
                time_label=time_label,
                detail=detail,
            )
        )

    audit_logs = [
        ("log-001", "10:15:32", "info", "Nexus Orchestrator", "Initiated Procure-to-Pay workflow for Acme Corp."),
        ("log-002", "10:16:01", "event", "Data Fetcher v4", "Successfully retrieved vendor profile from NetSuite."),
        ("log-003", "10:16:45", "warning", "Shield Verifier", "Signature missing on W-9 doc. Initiated self-correction module."),
        ("log-004", "10:17:10", "action", "Action Exec Alpha", "Drafted and sent missing signature request email to vendor."),
        ("log-005", "10:25:00", "escalation", "Nexus Orchestrator", "Globex contract stalled. SLA breach predicted in 2 hours. Escalated to Legal Lead."),
    ]
    for log_id, time_label, log_type, agent, message in audit_logs:
        session.add(
            AuditLog(
                id=log_id,
                time_label=time_label,
                log_type=log_type,
                agent=agent,
                message=message,
            )
        )

    employees = [
        ("emp-1", "Taniya Kundu", "Senior Engineer", "Engineering", "taniya.kundu@nexuscore.ai", "+1 (555) 234-5678", "San Francisco, CA", "Apr 15, 2026", "onboarding", 75, "TK"),
        ("emp-2", "Rupam Jana", "Backend Lead", "Engineering", "rupam.jana@nexuscore.ai", "+1 (555) 567-8901", "New York, NY", "Jan 10, 2026", "active", 100, "RJ"),
        ("emp-3", "James Rodriguez", "Product Manager", "Product", "james.rodriguez@nexuscore.ai", "+1 (555) 345-6789", "Seattle, WA", "Mar 01, 2026", "active", 100, "JR"),
        ("emp-4", "Cassandra Vale", "UX Designer", "Design", "cassandra.vale@nexuscore.ai", "+1 (555) 456-7890", "Austin, TX", "Feb 15, 2026", "active", 100, "CV"),
    ]
    for employee in employees:
        session.add(
            Employee(
                id=employee[0],
                name=employee[1],
                role=employee[2],
                department=employee[3],
                email=employee[4],
                phone=employee[5],
                location=employee[6],
                start_date_label=employee[7],
                status=employee[8],
                progress=employee[9],
                avatar=employee[10],
            )
        )

    meetings = [
        (
            "mt-1",
            "Q3 Product Strategy Sync",
            "zoom",
            "Mar 28, 2026",
            "2:00 PM - 2:47 PM",
            "47 min",
            "analyzed",
            True,
            "MeetIntel Core",
            ["Sarah Chen", "James Rodriguez", "Cassandra Vale", "Rupam Jana"],
        ),
        (
            "mt-2",
            "Sprint 23 Retrospective",
            "gmeet",
            "Mar 27, 2026",
            "11:00 AM - 11:45 AM",
            "45 min",
            "analyzed",
            True,
            "MeetIntel Core",
            ["Rupam Jana", "Dev Team", "Scrum Master"],
        ),
        (
            "mt-3",
            "Globex Account Review",
            "teams",
            "Mar 26, 2026",
            "3:00 PM - 3:30 PM",
            "30 min",
            "analyzed",
            False,
            None,
            ["Sales Lead", "Account Manager", "VP Sales"],
        ),
        (
            "mt-5",
            "Weekly Engineering Standup",
            "gmeet",
            "Mar 29, 2026",
            "9:00 AM - 9:15 AM",
            "15 min",
            "live",
            True,
            "MeetIntel Core",
            ["Engineering Team"],
        ),
    ]
    for item in meetings:
        session.add(
            Meeting(
                id=item[0],
                title=item[1],
                provider=item[2],
                date_label=item[3],
                time_label=item[4],
                duration=item[5],
                status=item[6],
                agent_joined=item[7],
                agent_name=item[8],
                attendees=item[9],
            )
        )

    transcript_lines = [
        ("mt-1", 1, "2:01", "Sarah Chen", "Let's start with the API migration timeline. Are we on track for the April deadline?"),
        ("mt-1", 2, "2:02", "Rupam Jana", "We're about 70% through the migration. The auth service is done, but the billing API needs another two weeks."),
        ("mt-1", 3, "2:04", "Sarah Chen", "That pushes us past the deadline. Alex, can you pull in one more engineer to parallelize the billing work?"),
        ("mt-1", 4, "2:05", "Rupam Jana", "Yes, I'll grab someone from the platform team. We should be able to hit April 15th."),
        ("mt-1", 5, "2:18", "Sarah Chen", "Agreed. Let's go with Redis. Alex, write up a brief ADR by Friday."),
        ("mt-2", 1, "11:01", "Scrum Master", "Let's go around - what went well this sprint?"),
        ("mt-2", 2, "11:15", "Rupam Jana", "We need to quarantine flaky tests. I'll set up a separate test suite."),
        ("mt-3", 1, "3:01", "Sales Lead", "Globex contract renewal is due in 90 days. Current ARR is $1.2M."),
        ("mt-3", 2, "3:12", "VP Sales", "Prepare a proposal with the renewal and analytics upsell. Let's get it to them within two weeks."),
    ]
    for meeting_id, position, time_label, speaker, text in transcript_lines:
        session.add(
            TranscriptLine(
                meeting_id=meeting_id,
                position=position,
                time_label=time_label,
                speaker=speaker,
                text=text,
            )
        )

    meeting_items = [
        ("mt-1", "decision", "Use Redis over Memcached for caching layer", "Rupam Jana", "decided", None, None),
        ("mt-1", "decision", "Target April 15th for API migration completion", "Rupam Jana", "decided", None, None),
        ("mt-1", "action", "Pull in engineer from platform team for billing API", "Rupam Jana", "in-progress", "Mar 29", 1),
        ("mt-1", "action", "Write ADR for Redis caching decision", "Rupam Jana", "pending", "Apr 4", 7),
        ("mt-1", "escalation", "Billing API migration behind schedule - resource needed", "Sarah Chen", "resolved", None, None),
        ("mt-2", "decision", "Quarantine flaky integration tests into separate suite", "Rupam Jana", "decided", None, None),
        ("mt-2", "action", "Set up flaky test quarantine suite", "Rupam Jana", "pending", "Apr 5", 6),
        ("mt-3", "decision", "Offer 3-year renewal with 5% volume discount to Globex", "VP Sales", "decided", None, None),
        ("mt-3", "action", "Prepare renewal and upsell proposal for Globex", "Account Manager", "pending", "Apr 9", 10),
    ]
    for meeting_id, item_type, text, owner, status, deadline, days_left in meeting_items:
        session.add(
            MeetingItem(
                meeting_id=meeting_id,
                item_type=item_type,
                text=text,
                owner=owner,
                status=status,
                deadline_label=deadline,
                days_left=days_left,
            )
        )

    sla_records = [
        ("sla-1", "Acme Corp Invoice Processing", "Procure-to-Pay", 4, 2.8, "on-track", "Manager Approval", "Nexus Orchestrator", "Will complete 45 min before SLA deadline", 92, None),
        ("sla-2", "Globex Contract Renewal", "Contract Lifecycle", 48, 46, "at-risk", "Legal Review", "Human (Legal)", "SLA breach in 2h 00m - auto-escalation triggered", 28, "Reassigned to Senior Legal Counsel + sent executive notification"),
        ("sla-3", "Taniya Kundu Onboarding", "Employee Onboarding", 24, 3.5, "on-track", "IT Provisioning", "Action Exec Alpha", "On track - 85% of steps already automated", 98, None),
        ("sla-4", "Q3 Vendor Audit", "Compliance", 72, 68, "breached", "Document Collection", "Data Fetcher v4", "SLA breached 4h ago - root cause: vendor non-responsive", 5, "Escalated to VP Procurement + vendor penalty clause activated"),
    ]
    for record in sla_records:
        session.add(
            SlaRecord(
                id=record[0],
                name=record[1],
                workflow_type=record[2],
                sla_hours=record[3],
                elapsed_hours=record[4],
                status=record[5],
                current_step=record[6],
                agent=record[7],
                prediction=record[8],
                health=record[9],
                auto_action=record[10],
            )
        )

    bottlenecks = [
        ("Legal Review", "18h", "3x this week", "high", "Implement parallel legal review with 2nd counsel"),
        ("Vendor Response", "36h", "5x this month", "high", "Auto-send follow-ups at 12h and 24h marks"),
        ("Manager Approval", "4h", "8x this week", "medium", "Enable Slack one-click approval for amounts < $50K"),
        ("Document Upload", "2h", "12x this week", "low", "Deploy OCR auto-parser for common document types"),
    ]
    for area, avg_delay, frequency, risk, suggestion in bottlenecks:
        session.add(
            Bottleneck(
                area=area,
                avg_delay=avg_delay,
                frequency=frequency,
                risk=risk,
                suggestion=suggestion,
            )
        )

    tools = [
        ("tool-calendar", "Calendar Control", "calendar", "Schedules approvals, follow-ups, and meeting events.", "connected", "calendar-mcp", ["create_event", "schedule_follow_up", "list_events"]),
        ("tool-task", "Task Manager", "tasks", "Creates and tracks work items across workflows.", "connected", "task-manager-mcp", ["create_task", "route_workflow", "update_status"]),
        ("tool-notes", "Notes Workspace", "notes", "Stores meeting summaries and extracted notes.", "connected", "notes-mcp", ["write_note", "summarize_meeting", "search_notes"]),
        ("tool-knowledge", "Knowledge Base", "search", "Retrieves employee, vendor, and contract context.", "connected", "knowledge-mcp", ["retrieve_context", "search_records"]),
        ("tool-compliance", "Compliance Vault", "compliance", "Runs policy, risk, and audit checks.", "connected", "compliance-mcp", ["run_check", "store_audit_record"]),
    ]
    for tool_id, name, tool_type, description, status, server, capabilities in tools:
        session.add(
            ToolConnection(
                id=tool_id,
                name=name,
                tool_type=tool_type,
                description=description,
                status=status,
                mcp_server=server,
                capabilities=capabilities,
            )
        )

    await session.commit()
    await seed_phase1_extensions(session)


async def seed_phase1_extensions(session: AsyncSession) -> None:
    existing_conversation = await session.scalar(select(Conversation.id).limit(1))
    if existing_conversation:
        return

    conversations = [
        Conversation(
            id="conv-001",
            title="Vendor onboarding escalation",
            status="active",
            owner_user_id="u-2",
            primary_agent_id="ag-orchestrator",
            workflow_id="wf-901",
        ),
        Conversation(
            id="conv-002",
            title="Employee onboarding coordination",
            status="active",
            owner_user_id="u-6",
            primary_agent_id="ag-orchestrator",
            workflow_id="wf-902",
        ),
    ]
    session.add_all(conversations)

    messages = [
        ConversationMessage(
            id="msg-001",
            conversation_id="conv-001",
            role="user",
            sender_name="Sarah Chen",
            content="Please verify Acme Corp and move the purchase request forward today.",
        ),
        ConversationMessage(
            id="msg-002",
            conversation_id="conv-001",
            role="assistant",
            sender_name="Nexus Orchestrator",
            agent_id="ag-orchestrator",
            content="I delegated vendor verification to Data Fetcher and queued the approval path with Shield Verifier.",
        ),
        ConversationMessage(
            id="msg-003",
            conversation_id="conv-002",
            role="user",
            sender_name="Maria Lopez",
            content="Onboard Priya Nair as a Software Engineer in Engineering starting Apr 20, 2026.",
        ),
        ConversationMessage(
            id="msg-004",
            conversation_id="conv-002",
            role="assistant",
            sender_name="Nexus Orchestrator",
            agent_id="ag-orchestrator",
            content="Identity, provisioning, and orientation setup have been split across the specialist agents.",
        ),
    ]
    session.add_all(messages)

    tasks = [
        AgentTask(
            id="task-001",
            title="Vendor verification",
            description="Validate the Acme Corp vendor profile and return readiness for approval.",
            status="completed",
            priority="high",
            assigned_agent_id="ag-retrieval",
            requested_by_user_id="u-2",
            conversation_id="conv-001",
            workflow_id="wf-901",
            input_payload={"vendor": "Acme Corp"},
            result_payload={"result": "vendor verified"},
        ),
        AgentTask(
            id="task-002",
            title="Compliance review",
            description="Run a compliance pass over the procurement package and identify missing artifacts.",
            status="completed",
            priority="high",
            assigned_agent_id="ag-verifier",
            requested_by_user_id="u-2",
            conversation_id="conv-001",
            workflow_id="wf-901",
            input_payload={"workflowId": "wf-901"},
            result_payload={"result": "missing W-9 signature"},
        ),
        AgentTask(
            id="task-003",
            title="Orientation scheduling",
            description="Create the Day 1 orientation event and notify the new employee.",
            status="completed",
            priority="normal",
            assigned_agent_id="ag-executor",
            requested_by_user_id="u-6",
            conversation_id="conv-002",
            workflow_id="wf-902",
            input_payload={"employee": "Priya Nair"},
            result_payload={"result": "calendar event scheduled"},
        ),
    ]
    session.add_all(tasks)

    runs = [
        AgentRun(
            id="run-001",
            agent_id="ag-orchestrator",
            task_id="task-001",
            conversation_id="conv-001",
            workflow_id="wf-901",
            status="completed",
            run_type="orchestration",
            input_summary="Route the procurement request to the right specialist agent.",
            output_summary="Assigned vendor verification to Data Fetcher v4.",
            duration_ms=900,
            completed_at=datetime.now(UTC),
        ),
        AgentRun(
            id="run-002",
            agent_id="ag-retrieval",
            task_id="task-001",
            conversation_id="conv-001",
            workflow_id="wf-901",
            status="completed",
            run_type="retrieval",
            input_summary="Fetch vendor records for Acme Corp.",
            output_summary="Vendor profile confirmed in the knowledge base.",
            duration_ms=1600,
            completed_at=datetime.now(UTC),
        ),
        AgentRun(
            id="run-003",
            agent_id="ag-verifier",
            task_id="task-002",
            conversation_id="conv-001",
            workflow_id="wf-901",
            status="completed",
            run_type="verification",
            input_summary="Check procurement packet for compliance gaps.",
            output_summary="Detected and logged a missing W-9 signature.",
            duration_ms=2100,
            completed_at=datetime.now(UTC),
        ),
        AgentRun(
            id="run-004",
            agent_id="ag-executor",
            task_id="task-003",
            conversation_id="conv-002",
            workflow_id="wf-902",
            status="completed",
            run_type="execution",
            input_summary="Schedule Day 1 orientation for Priya Nair.",
            output_summary="Orientation event created and noted in the workflow.",
            duration_ms=1750,
            completed_at=datetime.now(UTC),
        ),
    ]
    session.add_all(runs)

    handoffs = [
        AgentHandoff(
            id="handoff-001",
            from_agent_id="ag-orchestrator",
            to_agent_id="ag-retrieval",
            task_id="task-001",
            conversation_id="conv-001",
            workflow_id="wf-901",
            reason="Retrieve vendor context before approval routing.",
            status="accepted",
        ),
        AgentHandoff(
            id="handoff-002",
            from_agent_id="ag-orchestrator",
            to_agent_id="ag-verifier",
            task_id="task-002",
            conversation_id="conv-001",
            workflow_id="wf-901",
            reason="Validate compliance posture before payment execution.",
            status="accepted",
        ),
        AgentHandoff(
            id="handoff-003",
            from_agent_id="ag-orchestrator",
            to_agent_id="ag-executor",
            task_id="task-003",
            conversation_id="conv-002",
            workflow_id="wf-902",
            reason="Complete the final scheduling step for onboarding.",
            status="accepted",
        ),
    ]
    session.add_all(handoffs)

    invocations = [
        ToolInvocation(
            id="inv-001",
            tool_id="tool-knowledge",
            tool_name="Knowledge Base",
            action="retrieve_context",
            status="ok",
            summary="Knowledge Base retrieved Acme Corp records and vendor master data.",
            payload={"vendor": "Acme Corp"},
            conversation_id="conv-001",
            workflow_id="wf-901",
            agent_run_id="run-002",
        ),
        ToolInvocation(
            id="inv-002",
            tool_id="tool-compliance",
            tool_name="Compliance Vault",
            action="run_check",
            status="ok",
            summary="Compliance Vault detected a missing signature on the W-9 artifact.",
            payload={"workflowId": "wf-901"},
            conversation_id="conv-001",
            workflow_id="wf-901",
            agent_run_id="run-003",
        ),
        ToolInvocation(
            id="inv-003",
            tool_id="tool-calendar",
            tool_name="Calendar Control",
            action="create_event",
            status="ok",
            summary="Calendar Control scheduled Day 1 orientation for Priya Nair.",
            payload={"employee": "Priya Nair"},
            conversation_id="conv-002",
            workflow_id="wf-902",
            agent_run_id="run-004",
        ),
    ]
    session.add_all(invocations)

    await session.commit()
