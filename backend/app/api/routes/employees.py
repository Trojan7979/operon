from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import User
from app.db.session import get_db_session
from app.schemas import CreateEmployeeRequest, EmployeeOut, UpdateEmployeeRequest
from app.services.employees import (
    EmployeeDomainError,
    EmployeeConflictError,
    EmployeeStatus,
    create_employee_record,
    create_onboarding_workflow_artifacts,
    get_employee,
    list_employees as list_employees_query,
    update_employee_record,
)
from app.services.serializers import serialize_employee

router = APIRouter()


@router.get("", response_model=list[EmployeeOut])
async def list_employees(
    employee_status: Annotated[EmployeeStatus | None, Query(alias="status")] = None,
    department: str | None = None,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[EmployeeOut]:
    employees = await list_employees_query(
        session,
        employee_status=employee_status,
        department=department,
    )
    return [EmployeeOut.model_validate(serialize_employee(employee)) for employee in employees]


@router.post("", response_model=EmployeeOut, status_code=201)
async def create_employee(
    payload: CreateEmployeeRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> EmployeeOut:
    try:
        employee = await create_employee_record(
            session,
            name=payload.name,
            role=payload.role,
            department=payload.department,
            email=payload.email,
            phone=payload.phone,
            location=payload.location,
            start_date=payload.startDate,
            photo_url=payload.photoUrl,
            status=EmployeeStatus.ONBOARDING,
        )
        await create_onboarding_workflow_artifacts(
            session,
            employee_name=payload.name,
            department=payload.department,
            agent_name=current_user.name,
        )
        await session.commit()
    except EmployeeConflictError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except EmployeeDomainError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except SQLAlchemyError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create employee record. Please check the backend database schema.",
        )

    await session.refresh(employee)
    return EmployeeOut.model_validate(serialize_employee(employee))


@router.patch("/{employee_id}", response_model=EmployeeOut)
async def update_employee(
    employee_id: str,
    payload: UpdateEmployeeRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> EmployeeOut:
    employee = await get_employee(session, employee_id)
    if employee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found.")

    raw_updates = payload.model_dump(exclude_unset=True)
    force_status_override = raw_updates.pop("forceStatusOverride", False)
    if not raw_updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one employee field must be updated.",
        )

    mapped_updates: dict = {}
    if "name" in raw_updates:
        mapped_updates["name"] = raw_updates["name"]
    if "role" in raw_updates:
        mapped_updates["role"] = raw_updates["role"]
    if "department" in raw_updates:
        mapped_updates["department"] = raw_updates["department"]
    if "email" in raw_updates:
        mapped_updates["email"] = raw_updates["email"]
    if "phone" in raw_updates:
        mapped_updates["phone"] = raw_updates["phone"]
    if "location" in raw_updates:
        mapped_updates["location"] = raw_updates["location"]
    if "startDate" in raw_updates:
        mapped_updates["start_date"] = raw_updates["startDate"]
    if "status" in raw_updates:
        mapped_updates["status"] = raw_updates["status"]
    if "progress" in raw_updates:
        mapped_updates["progress"] = raw_updates["progress"]
    if "photoUrl" in raw_updates:
        mapped_updates["photo_url"] = raw_updates["photoUrl"]

    try:
        await update_employee_record(
            session,
            employee,
            updates=mapped_updates,
            actor_name=current_user.name,
            force_status_override=force_status_override,
        )
        await session.commit()
    except EmployeeConflictError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except EmployeeDomainError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    await session.refresh(employee)
    return EmployeeOut.model_validate(serialize_employee(employee))
