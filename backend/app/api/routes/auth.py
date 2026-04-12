from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    get_password_hash,
    get_refresh_token_expiry,
    hash_token,
    verify_password,
)
from app.db.models import AuthSession, User
from app.db.seed import ROLE_TEMPLATES
from app.db.session import get_db_session
from app.schemas import (
    LoginRequest,
    LogoutRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.services.serializers import serialize_user

router = APIRouter()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def build_avatar(name: str) -> str:
    parts = [part for part in name.split() if part]
    return "".join(part[0] for part in parts[:2]).upper() or "U"


async def authenticate_user(email: str, password: str, session: AsyncSession) -> User:
    normalized_email = normalize_email(email)
    user = await session.scalar(select(User).where(User.email == normalized_email))
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This user account is not active.",
        )
    return user


def build_token_response(user: User, refresh_token: str | None = None) -> TokenResponse:
    token = create_access_token(user.email)
    return TokenResponse(
        access_token=token,
        refreshToken=refresh_token,
        user=UserOut.model_validate(serialize_user(user)),
    )


async def create_refresh_session(user: User, session: AsyncSession) -> str:
    refresh_token = create_refresh_token()
    session.add(
        AuthSession(
            id=f"auth-{uuid4().hex[:10]}",
            user_id=user.id,
            refresh_token_hash=hash_token(refresh_token),
            status="active",
            expires_at=get_refresh_token_expiry(),
            last_used_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
    )
    return refresh_token


async def revoke_user_sessions(
    user_id: str,
    session: AsyncSession,
    *,
    refresh_token: str | None = None,
) -> int:
    query = select(AuthSession).where(AuthSession.user_id == user_id, AuthSession.status == "active")
    sessions = list(await session.scalars(query))
    revoked = 0
    token_hash = hash_token(refresh_token) if refresh_token else None
    for auth_session in sessions:
        if token_hash and auth_session.refresh_token_hash != token_hash:
            continue
        auth_session.status = "revoked"
        auth_session.revoked_at = datetime.now(UTC)
        revoked += 1
    return revoked


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(
    payload: RegisterRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    normalized_email = normalize_email(payload.email)
    normalized_name = payload.name.strip()
    normalized_department = payload.department.strip()
    normalized_role = payload.role.strip()

    if normalized_role not in ROLE_TEMPLATES:
        raise HTTPException(status_code=400, detail="Unsupported role.")

    existing_user = await session.scalar(select(User).where(User.email == normalized_email))
    if existing_user is not None:
        raise HTTPException(status_code=409, detail="A user with that email already exists.")

    permissions = ROLE_TEMPLATES[normalized_role]
    user = User(
        id=f"u-{uuid4().hex[:8]}",
        name=normalized_name,
        email=normalized_email,
        password_hash=get_password_hash(payload.password),
        role=normalized_role,
        avatar=build_avatar(normalized_name),
        status="active",
        department=normalized_department,
        permissions=permissions,
    )
    session.add(user)
    refresh_token = await create_refresh_session(user, session)
    await session.commit()
    await session.refresh(user)
    return build_token_response(user, refresh_token)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: AsyncSession = Depends(get_db_session)) -> TokenResponse:
    user = await authenticate_user(payload.email, payload.password, session)
    refresh_token = await create_refresh_session(user, session)
    await session.commit()
    return build_token_response(user, refresh_token)


@router.post("/token", response_model=TokenResponse)
async def token_login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    user = await authenticate_user(form_data.username, form_data.password, session)
    refresh_token = await create_refresh_session(user, session)
    await session.commit()
    return build_token_response(user, refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshTokenRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    refresh_token_value = payload.refreshToken.strip()
    if not refresh_token_value:
        raise HTTPException(status_code=400, detail="Refresh token is required.")

    auth_session = await session.scalar(
        select(AuthSession).where(
            AuthSession.refresh_token_hash == hash_token(refresh_token_value),
            AuthSession.status == "active",
        )
    )
    if auth_session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token is invalid.")
    if auth_session.expires_at <= datetime.now(UTC):
        auth_session.status = "expired"
        auth_session.revoked_at = datetime.now(UTC)
        await session.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token is expired.")

    user = await session.get(User, auth_session.user_id)
    if user is None or user.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User session is invalid.")

    auth_session.status = "rotated"
    auth_session.revoked_at = datetime.now(UTC)
    auth_session.last_used_at = datetime.now(UTC)
    refresh_token = await create_refresh_session(user, session)
    await session.commit()
    return build_token_response(user, refresh_token)


@router.post("/logout")
async def logout(
    payload: LogoutRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    refresh_token_value = payload.refreshToken.strip() if payload.refreshToken else None
    revoked = await revoke_user_sessions(
        current_user.id,
        session,
        refresh_token=refresh_token_value,
    )
    if refresh_token_value and revoked == 0:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token is invalid.")
    await session.commit()
    return {"status": "ok", "revokedSessions": revoked}


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(serialize_user(current_user))
