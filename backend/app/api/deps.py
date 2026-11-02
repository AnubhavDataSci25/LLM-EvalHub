"""Shared FastAPI dependencies for DB sessions, pagination, auth, and multi-tenant workspaces."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, Any, Literal, TypeVar

from fastapi import Depends, Header, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import AuthenticationError, ForbiddenError, NotFoundError
from app.core.security import decode_access_token
from app.db.init_db import seed_default_workspace_and_user
from app.db.session import get_db
from app.models.auth import User, Workspace, WorkspaceMember

T = TypeVar("T")

ROLE_HIERARCHY: dict[str, int] = {
    "viewer": 1,
    "editor": 2,
    "owner": 3,
}


def db_session() -> Iterator[Session]:
    yield from get_db()


DbSession = Annotated[Session, Depends(db_session)]


class Pagination:
    def __init__(
        self,
        limit: int = Query(50, ge=1, le=200, description="Maximum rows to return"),
        offset: int = Query(0, ge=0, description="Rows to skip"),
    ) -> None:
        self.limit = limit
        self.offset = offset


PageParams = Annotated[Pagination, Depends(Pagination)]


class WorkspaceContext:
    """Encapsulates the authenticated user, active tenant workspace, and membership role."""

    def __init__(
        self,
        user: User,
        workspace: Workspace,
        role: Literal["owner", "editor", "viewer"],
        db: Session,
        membership: WorkspaceMember | None = None,
    ) -> None:
        self.user = user
        self.workspace = workspace
        self.role = role
        self.db = db
        self.membership = membership

    def require_role(self, min_role: Literal["owner", "editor", "viewer"]) -> None:
        """Enforces minimum RBAC role. Raises ForbiddenError if below threshold."""
        user_level = ROLE_HIERARCHY.get(self.role, 0)
        min_level = ROLE_HIERARCHY.get(min_role, 0)
        if user_level < min_level:
            raise ForbiddenError(
                f"Action requires '{min_role}' role or higher; current role is '{self.role}'"
            )

    def get_or_404(self, model_cls: type[T], entity_id: str) -> T:
        """Fetch an entity by ID scoped strictly to this workspace.

        Returns 404 (never 403) on cross-tenant attempts to prevent existence leakage.
        """
        entity = self.db.get(model_cls, entity_id)
        if not entity:
            raise NotFoundError(f"{model_cls.__name__} {entity_id} not found")

        # Verify tenant ownership if model has workspace_id
        entity_wks = getattr(entity, "workspace_id", None)
        if entity_wks is not None and entity_wks != self.workspace.id:
            raise NotFoundError(f"{model_cls.__name__} {entity_id} not found")

        return entity

    def scope_query(self, query: Any, model_cls: type[T]) -> Any:
        """Applies workspace isolation filter to a SQLAlchemy query."""
        if hasattr(model_cls, "workspace_id"):
            return query.where(model_cls.workspace_id == self.workspace.id)
        return query


def get_current_user(
    request: Request,
    db: Session = Depends(db_session),
) -> User:
    """Resolves authenticated user from Bearer JWT.

    In local mode with no token, transparently falls back to usr_default.
    """
    auth_header = request.headers.get("Authorization")
    token: str | None = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()

    if token:
        try:
            payload = decode_access_token(token)
            user_id = payload.get("sub")
            if not user_id:
                raise AuthenticationError("Invalid authentication token")
        except Exception as exc:
            raise AuthenticationError(f"Invalid or expired token: {exc}") from exc

        user = db.get(User, user_id)
        if not user or not user.is_active:
            raise AuthenticationError("User account not found or deactivated")
        return user

    # If no token provided:
    if settings.is_auth_enabled:
        raise AuthenticationError("Authentication required")

    # Local single-user mode: return default user
    default_user = db.get(User, "usr_default")
    if not default_user:
        seed_default_workspace_and_user(db)
        default_user = db.get(User, "usr_default")
        if not default_user:
            raise AuthenticationError("Failed to initialize local mode user")
    return default_user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_workspace_context(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(db_session),
    x_workspace_id: str | None = Header(None, alias="X-Workspace-Id"),
    workspace_id_query: str | None = Query(None, alias="workspace_id"),
) -> WorkspaceContext:
    """Resolves active workspace context and validates membership role.

    Resolution precedence:
    1. X-Workspace-Id header
    2. ?workspace_id= query param
    3. User's first workspace membership
    4. Default workspace in local mode
    """
    target_id = x_workspace_id or workspace_id_query

    if not target_id:
        if not settings.is_auth_enabled:
            target_id = "wks_default"
        else:
            # Pick user's first workspace
            membership = db.scalar(
                select(WorkspaceMember)
                .where(WorkspaceMember.user_id == user.id)
                .order_by(WorkspaceMember.created_at.asc())
            )
            if membership:
                target_id = membership.workspace_id
            else:
                target_id = "wks_default"

    workspace = db.get(Workspace, target_id)
    if not workspace:
        # In local mode, ensure seed exists
        if not settings.is_auth_enabled and target_id == "wks_default":
            seed_default_workspace_and_user(db)
            workspace = db.get(Workspace, "wks_default")

        if not workspace:
            raise NotFoundError(f"Workspace {target_id} not found")

    # Resolve membership and role
    if not settings.is_auth_enabled and user.id == "usr_default":
        # Always owner in local mode
        return WorkspaceContext(
            user=user,
            workspace=workspace,
            role="owner",
            db=db,
            membership=None,
        )

    if user.is_superuser:
        return WorkspaceContext(
            user=user,
            workspace=workspace,
            role="owner",
            db=db,
            membership=None,
        )

    membership = db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == user.id,
        )
    )

    if not membership:
        # Return 404 to avoid leaking existence of private workspaces
        raise NotFoundError(f"Workspace {target_id} not found")

    return WorkspaceContext(
        user=user,
        workspace=workspace,
        role=membership.role,
        db=db,
        membership=membership,
    )


CurrentWorkspaceContext = Annotated[WorkspaceContext, Depends(get_workspace_context)]


def require_role(min_role: Literal["owner", "editor", "viewer"]):
    """Dependency factory ensuring user has at least min_role in current workspace."""

    def _role_checker(ctx: WorkspaceContext = Depends(get_workspace_context)) -> WorkspaceContext:
        ctx.require_role(min_role)
        return ctx

    return _role_checker


RequireEditor = Annotated[WorkspaceContext, Depends(require_role("editor"))]
RequireOwner = Annotated[WorkspaceContext, Depends(require_role("owner"))]
