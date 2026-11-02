"""Authentication API endpoints (register, login, refresh, logout, profile)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, status

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.exceptions import RateLimitExceededError
from app.core.security import auth_limiter
from app.schemas.auth import (
    RefreshTokenRequest,
    TokenResponse,
    UserLoginRequest,
    UserRead,
    UserRegisterRequest,
    UserWithWorkspaces,
)
from app.services.auth_service import AuthService
from app.services.workspace_service import WorkspaceService

logger = logging.getLogger(__name__)

auth_router = APIRouter(prefix="/auth", tags=["auth"])


def _check_auth_rate_limit(request: Request, action: str) -> None:
    client_ip = request.client.host if request.client else "unknown"
    key = f"{action}:{client_ip}"
    if not auth_limiter.is_allowed(key):
        retry_after = auth_limiter.retry_after(key)
        raise RateLimitExceededError(
            f"Too many {action} attempts. Please try again in {retry_after} seconds."
        )


@auth_router.get("/mode")
def get_auth_mode() -> dict[str, str | bool]:
    """Returns current auth configuration mode for the frontend."""
    return {
        "mode": settings.auth_mode,
        "is_auth_enabled": settings.is_auth_enabled,
    }


@auth_router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: UserRegisterRequest,
    request: Request,
    db: DbSession,
) -> UserRead:
    _check_auth_rate_limit(request, "register")
    service = AuthService(db)
    user, _ = service.register(
        email=str(payload.email),
        password=payload.password,
        full_name=payload.full_name,
    )
    return UserRead.model_validate(user)


@auth_router.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    payload: UserLoginRequest,
    request: Request,
    db: DbSession,
) -> TokenResponse:
    _check_auth_rate_limit(request, "login")
    client_ip = request.client.host if request.client else "unknown"
    service = AuthService(db)
    _, tokens = service.login(str(payload.email), payload.password, client_ip=client_ip)
    return tokens


@auth_router.post(
    "/refresh",
    response_model=TokenResponse,
)
def refresh_token(
    payload: RefreshTokenRequest,
    db: DbSession,
) -> TokenResponse:
    service = AuthService(db)
    return service.refresh(payload.refresh_token)


@auth_router.post("/logout")
def logout(
    payload: RefreshTokenRequest,
    db: DbSession,
) -> dict[str, str]:
    service = AuthService(db)
    service.logout(payload.refresh_token)
    return {"status": "logged_out"}


@auth_router.get("/me", response_model=UserWithWorkspaces)
def get_current_user_profile(
    user: CurrentUser,
    db: DbSession,
) -> UserWithWorkspaces:
    wks_service = WorkspaceService(db)

    workspaces = wks_service.list_user_workspaces(user)
    active_id = workspaces[0].id if workspaces else None

    return UserWithWorkspaces(
        user=UserRead.model_validate(user),
        workspaces=workspaces,
        active_workspace_id=active_id,
    )
