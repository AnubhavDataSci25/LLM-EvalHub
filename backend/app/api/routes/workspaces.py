"""Workspace, RBAC membership, and encrypted provider key API endpoints."""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import ForbiddenError, NotFoundError
from app.schemas.audit_log import AuditLogListResponse, AuditLogRead
from app.schemas.auth import (
    WorkspaceCreateRequest,
    WorkspaceMemberInviteRequest,
    WorkspaceMemberRead,
    WorkspaceMemberUpdateRequest,
    WorkspaceProviderKeySetRequest,
    WorkspaceProviderStatusRead,
    WorkspaceRead,
    WorkspaceUpdateRequest,
)
from app.services.audit_log_service import AuditLogService
from app.services.workspace_service import WorkspaceService

logger = logging.getLogger(__name__)

workspace_router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def _check_workspace_role(
    wks_service: WorkspaceService,
    workspace_id: str,
    user_id: str,
    min_role: Literal["owner", "editor", "viewer"] = "viewer",
) -> None:
    """Verifies user belongs to workspace and has required role, else raises 404 or 403."""
    user = wks_service.db.get(CurrentUser.__args__[0], user_id) if hasattr(CurrentUser, "__args__") else None
    if user and user.is_superuser:
        return

    membership = wks_service.get_membership(workspace_id, user_id)
    if not membership:
        raise NotFoundError(f"Workspace {workspace_id} not found")

    role_hierarchy = {"viewer": 1, "editor": 2, "owner": 3}
    if role_hierarchy.get(membership.role, 0) < role_hierarchy.get(min_role, 0):
        raise ForbiddenError(f"Requires '{min_role}' role or higher in this workspace")


@workspace_router.get("", response_model=list[WorkspaceRead])
def list_workspaces(
    user: CurrentUser,
    db: DbSession,
) -> list[WorkspaceRead]:
    service = WorkspaceService(db)
    return service.list_user_workspaces(user)


@workspace_router.post(
    "",
    response_model=WorkspaceRead,
    status_code=status.HTTP_201_CREATED,
)
def create_workspace(
    payload: WorkspaceCreateRequest,
    user: CurrentUser,
    db: DbSession,
) -> WorkspaceRead:
    service = WorkspaceService(db)
    w = service.create_workspace(user, payload)
    return WorkspaceRead(
        id=w.id,
        name=w.name,
        slug=w.slug,
        description=w.description,
        created_at=w.created_at,
        current_user_role="owner",
        member_count=1,
    )


@workspace_router.get("/{workspace_id}", response_model=WorkspaceRead)
def get_workspace(
    workspace_id: str,
    user: CurrentUser,
    db: DbSession,
) -> WorkspaceRead:
    service = WorkspaceService(db)
    _check_workspace_role(service, workspace_id, user.id, "viewer")
    w = service.get_workspace_or_404(workspace_id)
    membership = service.get_membership(workspace_id, user.id)
    members = service.list_members(workspace_id)
    return WorkspaceRead(
        id=w.id,
        name=w.name,
        slug=w.slug,
        description=w.description,
        created_at=w.created_at,
        current_user_role=membership.role if membership else ("owner" if user.is_superuser else None),
        member_count=len(members),
    )


@workspace_router.put("/{workspace_id}", response_model=WorkspaceRead)
def update_workspace(
    workspace_id: str,
    payload: WorkspaceUpdateRequest,
    user: CurrentUser,
    db: DbSession,
) -> WorkspaceRead:
    service = WorkspaceService(db)
    _check_workspace_role(service, workspace_id, user.id, "owner")
    w = service.get_workspace_or_404(workspace_id)
    updated = service.update_workspace(w, payload)
    membership = service.get_membership(workspace_id, user.id)
    members = service.list_members(workspace_id)
    return WorkspaceRead(
        id=updated.id,
        name=updated.name,
        slug=updated.slug,
        description=updated.description,
        created_at=updated.created_at,
        current_user_role=membership.role if membership else None,
        member_count=len(members),
    )


@workspace_router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workspace(
    workspace_id: str,
    user: CurrentUser,
    db: DbSession,
) -> None:
    service = WorkspaceService(db)
    _check_workspace_role(service, workspace_id, user.id, "owner")
    w = service.get_workspace_or_404(workspace_id)
    AuditLogService.log(
        db,
        workspace_id=workspace_id,
        user_id=user.id,
        actor_email=user.email,
        action="workspace.delete",
        resource_type="workspace",
        resource_id=workspace_id,
        details={"name": w.name, "slug": w.slug},
    )
    service.delete_workspace(w)


# --- Members ------------------------------------------------------------------


@workspace_router.get("/{workspace_id}/members", response_model=list[WorkspaceMemberRead])
def list_workspace_members(
    workspace_id: str,
    user: CurrentUser,
    db: DbSession,
) -> list[WorkspaceMemberRead]:
    service = WorkspaceService(db)
    _check_workspace_role(service, workspace_id, user.id, "viewer")
    return service.list_members(workspace_id)


@workspace_router.post(
    "/{workspace_id}/members",
    response_model=WorkspaceMemberRead,
    status_code=status.HTTP_201_CREATED,
)
def invite_workspace_member(
    workspace_id: str,
    payload: WorkspaceMemberInviteRequest,
    user: CurrentUser,
    db: DbSession,
) -> WorkspaceMemberRead:
    service = WorkspaceService(db)
    _check_workspace_role(service, workspace_id, user.id, "owner")
    member = service.add_or_invite_member(workspace_id, payload)
    AuditLogService.log(
        db,
        workspace_id=workspace_id,
        user_id=user.id,
        actor_email=user.email,
        action="member.invite",
        resource_type="member",
        resource_id=member.user_id,
        details={"email": str(payload.email), "role": payload.role},
    )
    db.commit()
    return member


@workspace_router.put(
    "/{workspace_id}/members/{target_user_id}",
    response_model=WorkspaceMemberRead,
)
def update_workspace_member_role(
    workspace_id: str,
    target_user_id: str,
    payload: WorkspaceMemberUpdateRequest,
    user: CurrentUser,
    db: DbSession,
) -> WorkspaceMemberRead:
    service = WorkspaceService(db)
    _check_workspace_role(service, workspace_id, user.id, "owner")
    member = service.update_member_role(workspace_id, target_user_id, payload)
    AuditLogService.log(
        db,
        workspace_id=workspace_id,
        user_id=user.id,
        actor_email=user.email,
        action="member.role_update",
        resource_type="member",
        resource_id=target_user_id,
        details={"new_role": payload.role},
    )
    db.commit()
    return member


@workspace_router.delete(
    "/{workspace_id}/members/{target_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_workspace_member(
    workspace_id: str,
    target_user_id: str,
    user: CurrentUser,
    db: DbSession,
) -> None:
    service = WorkspaceService(db)
    _check_workspace_role(service, workspace_id, user.id, "owner")
    service.remove_member(workspace_id, target_user_id)
    AuditLogService.log(
        db,
        workspace_id=workspace_id,
        user_id=user.id,
        actor_email=user.email,
        action="member.remove",
        resource_type="member",
        resource_id=target_user_id,
    )
    db.commit()


# --- Encrypted Provider Keys --------------------------------------------------


@workspace_router.get(
    "/{workspace_id}/providers",
    response_model=list[WorkspaceProviderStatusRead],
)
def list_workspace_provider_keys(
    workspace_id: str,
    user: CurrentUser,
    db: DbSession,
) -> list[WorkspaceProviderStatusRead]:
    service = WorkspaceService(db)
    _check_workspace_role(service, workspace_id, user.id, "viewer")
    return service.list_provider_status(workspace_id)


@workspace_router.put(
    "/{workspace_id}/providers/{provider}",
    response_model=WorkspaceProviderStatusRead,
)
def set_workspace_provider_key(
    workspace_id: str,
    provider: str,
    payload: WorkspaceProviderKeySetRequest,
    user: CurrentUser,
    db: DbSession,
) -> WorkspaceProviderStatusRead:
    service = WorkspaceService(db)
    _check_workspace_role(service, workspace_id, user.id, "owner")
    res = service.set_provider_key(workspace_id, provider, payload.api_key)
    AuditLogService.log(
        db,
        workspace_id=workspace_id,
        user_id=user.id,
        actor_email=user.email,
        action="provider_key.update",
        resource_type="provider_key",
        resource_id=provider,
        details={"provider": provider},
    )
    db.commit()
    return res


@workspace_router.delete(
    "/{workspace_id}/providers/{provider}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_workspace_provider_key(
    workspace_id: str,
    provider: str,
    user: CurrentUser,
    db: DbSession,
) -> None:
    service = WorkspaceService(db)
    _check_workspace_role(service, workspace_id, user.id, "owner")
    service.delete_provider_key(workspace_id, provider)
    AuditLogService.log(
        db,
        workspace_id=workspace_id,
        user_id=user.id,
        actor_email=user.email,
        action="provider_key.delete",
        resource_type="provider_key",
        resource_id=provider,
        details={"provider": provider},
    )
    db.commit()


# --- Audit Logs --------------------------------------------------------------


@workspace_router.get(
    "/{workspace_id}/audit-logs",
    response_model=AuditLogListResponse,
    summary="List workspace security audit logs (owner only)",
)
def list_workspace_audit_logs(
    workspace_id: str,
    user: CurrentUser,
    db: DbSession,
    action: str | None = None,
    resource_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> AuditLogListResponse:
    service = WorkspaceService(db)
    _check_workspace_role(service, workspace_id, user.id, "owner")
    items, total = AuditLogService.list_logs(
        db,
        workspace_id,
        action=action,
        resource_type=resource_type,
        limit=limit,
        offset=offset,
    )
    return AuditLogListResponse(
        items=[AuditLogRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )
