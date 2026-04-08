from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import AuditLog, Employee, User, Workflow, WorkflowStep
from app.db.session import get_db_session
from app.schemas import CreateEmployeeRequest, EmployeeOut
from app.services.serializers import serialize_employee

router = APIRouter()


@router.get("", response_model=list[EmployeeOut])
async def list_employees(
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[EmployeeOut]:
    employees = list(await session.scalars(select(Employee).order_by(Employee.name)))
    return [EmployeeOut.model_validate(serialize_employee(employee)) for employee in employees]


@router.post("", response_model=EmployeeOut, status_code=201)
async def create_employee(
    payload: CreateEmployeeRequest,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> EmployeeOut:
    existing_employee = await session.scalar(select(Employee).where(Employee.email == payload.email))
    if existing_employee is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An employee with email {payload.email} already exists.",
        )

    employee = Employee(
        id=f"emp-{uuid4().hex[:8]}",
        name=payload.name,
        role=payload.role,
        department=payload.department,
        email=payload.email,
        phone=payload.phone,
        location=payload.location,
        start_date_label=payload.startDate,
        status="onboarding",
        progress=100,
        avatar="".join(part[0] for part in payload.name.split()[:2]).upper(),
        photo_url=payload.photoUrl,
    )
    session.add(employee)

    workflow = Workflow(
        id=f"wf-{uuid4().hex[:6]}",
        workflow_type="Employee Onboarding",
        name=f"{payload.name} ({payload.department})",
        status="completed",
        health=100,
        progress=100,
        current_step="Onboarding Complete",
        assigned_agent="Shield Verifier",
        prediction="Automated onboarding completed successfully.",
    )
    session.add(workflow)

    steps = [
        ("Identity Verification", "Shield Verifier"),
        ("Background Check Initiated", "Data Fetcher v4"),
        ("Google Workspace Account Created", "Action Exec Alpha"),
        ("Slack and GitHub Provisioned", "Action Exec Alpha"),
        ("Hardware Request Submitted", "Nexus Orchestrator"),
        ("Manager Notification Sent", "Action Exec Alpha"),
        ("Day 1 Calendar Created", "Action Exec Alpha"),
        ("Onboarding Complete", "Shield Verifier"),
    ]
    for index, (name, agent) in enumerate(steps, start=1):
        session.add(
            WorkflowStep(
                workflow_id=workflow.id,
                position=index,
                name=name,
                agent=agent,
                status="completed",
                time_label="auto",
            )
        )

    session.add(
        AuditLog(
            id=f"log-{uuid4().hex[:10]}",
            time_label="auto",
            log_type="action",
            agent="Nexus Orchestrator",
            message=f"Completed onboarding workflow for {payload.name}.",
        )
    )

    await session.commit()
    await session.refresh(employee)
    return EmployeeOut.model_validate(serialize_employee(employee))
