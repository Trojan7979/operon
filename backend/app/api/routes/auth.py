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


async def authenticate_user(email: str, password: str, session: AsyncSession) -> User:
    user = await session.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
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
    existing_user = await session.scalar(select(User).where(User.email == payload.email))
    if existing_user is not None:
        raise HTTPException(status_code=409, detail="A user with that email already exists.")

    permissions = ROLE_TEMPLATES.get(payload.role, ROLE_TEMPLATES["Product Manager"])
    user = User(
        id=f"u-{uuid4().hex[:8]}",
        name=payload.name,
        email=payload.email,
        password_hash=get_password_hash(payload.password),
        role=payload.role,
        avatar="".join(part[0] for part in payload.name.split()[:2]).upper(),
        status="active",
        department=payload.department,
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
    auth_session = await session.scalar(
        select(AuthSession).where(
            AuthSession.refresh_token_hash == hash_token(payload.refreshToken),
            AuthSession.status == "active",
        )
    )
    if auth_session is None or auth_session.expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token is invalid.")

    user = await session.get(User, auth_session.user_id)
    if user is None:
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
    revoked = await revoke_user_sessions(
        current_user.id,
        session,
        refresh_token=payload.refreshToken,
    )
    await session.commit()
    return {"status": "ok", "revokedSessions": revoked}


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(serialize_user(current_user))
