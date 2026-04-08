from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.security import create_access_token, verify_password
from app.db.models import User
from app.db.session import get_db_session
from app.schemas import LoginRequest, TokenResponse, UserOut
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


def build_token_response(user: User) -> TokenResponse:
    token = create_access_token(user.email)
    return TokenResponse(
        access_token=token,
        user=UserOut.model_validate(serialize_user(user)),
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: AsyncSession = Depends(get_db_session)) -> TokenResponse:
    user = await authenticate_user(payload.email, payload.password, session)
    return build_token_response(user)


@router.post("/token", response_model=TokenResponse)
async def token_login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    user = await authenticate_user(form_data.username, form_data.password, session)
    return build_token_response(user)


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(serialize_user(current_user))
