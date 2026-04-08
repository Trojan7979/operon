from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.security import get_password_hash
from app.db.models import User
from app.db.seed import ROLE_TEMPLATES
from app.db.session import get_db_session
from app.schemas import CreateUserRequest, UpdateUserAccessRequest, UserOut
from app.services.serializers import serialize_user

router = APIRouter()


@router.get("/users", response_model=list[UserOut])
async def list_users(
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[UserOut]:
    users = list(await session.scalars(select(User).order_by(User.name)))
    return [UserOut.model_validate(serialize_user(user)) for user in users]


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(
    payload: CreateUserRequest,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> UserOut:
    permissions = ROLE_TEMPLATES.get(payload.role, ROLE_TEMPLATES["Product Manager"])
    user = User(
        id=f"u-{uuid4().hex[:8]}",
        name=payload.name,
        email=payload.email,
        password_hash=get_password_hash("changeme123"),
        role=payload.role,
        avatar="".join(part[0] for part in payload.name.split()[:2]).upper(),
        status="active",
        department=payload.department,
        permissions=permissions,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return UserOut.model_validate(serialize_user(user))


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user_access(
    user_id: str,
    payload: UpdateUserAccessRequest,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> UserOut:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    if payload.role:
        user.role = payload.role
        user.permissions = ROLE_TEMPLATES.get(payload.role, user.permissions)
    if payload.permissions is not None:
        user.permissions = payload.permissions
    if payload.status:
        user.status = payload.status

    await session.commit()
    await session.refresh(user)
    return UserOut.model_validate(serialize_user(user))
