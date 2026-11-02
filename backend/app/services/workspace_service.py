"""Workspace and membership management service."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.security import decrypt_secret, encrypt_secret, mask_secret
from app.db.base import new_id
from app.models.auth import User, Workspace, WorkspaceMember, WorkspaceProviderKey
from app.schemas.auth import (
    WorkspaceCreateRequest,
    WorkspaceMemberInviteRequest,
    WorkspaceMemberRead,
    WorkspaceMemberUpdateRequest,
    WorkspaceProviderStatusRead,
    WorkspaceRead,
    WorkspaceUpdateRequest,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

SUPPORTED_PROVIDERS: tuple[str, ...] = (
    "gemini",
    "groq",
    "openrouter",
    "huggingface",
    "nvidia_nim",
    "ollama",
)

PROVIDER_DISPLAY_NAMES: dict[str, str] = {
    "gemini": "Google Gemini",
    "groq": "Groq",
    "openrouter": "OpenRouter",
    "huggingface": "Hugging Face",
    "nvidia_nim": "NVIDIA NIM",
    "ollama": "Ollama",
}

ENV_KEY_MAP: dict[str, str] = {
    "gemini": "gemini_api_key",
    "groq": "groq_api_key",
    "openrouter": "openrouter_api_key",
    "huggingface": "hf_api_key",
    "nvidia_nim": "nvidia_nim_api_key",
}


def _slugify(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\s-]", "", name).strip().lower()
    slug = re.sub(r"[\s_-]+", "-", cleaned)
    return slug[:48] or "workspace"


class WorkspaceService:
    """Handles workspace lifecycle, RBAC membership, and workspace provider keys."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # --- Workspaces -----------------------------------------------------------

    def create_workspace(self, user: User, payload: WorkspaceCreateRequest) -> Workspace:
        base_slug = _slugify(payload.name)
        slug = base_slug
        suffix = 1
        while self.db.scalar(select(Workspace).where(Workspace.slug == slug)):
            slug = f"{base_slug}-{suffix}"
            suffix += 1

        workspace = Workspace(
            id=new_id("wks"),
            name=payload.name.strip(),
            slug=slug,
            description=payload.description.strip() if payload.description else None,
        )
        self.db.add(workspace)
        self.db.flush()

        # Add creating user as workspace owner
        membership = WorkspaceMember(
            id=new_id("wkm"),
            workspace_id=workspace.id,
            user_id=user.id,
            role="owner",
        )
        self.db.add(membership)
        self.db.commit()
        self.db.refresh(workspace)
        return workspace

    def list_user_workspaces(self, user: User) -> list[WorkspaceRead]:
        memberships = self.db.scalars(
            select(WorkspaceMember).where(WorkspaceMember.user_id == user.id)
        ).all()
        if not memberships:
            return []

        wks_ids = [m.workspace_id for m in memberships]
        role_by_wks = {m.workspace_id: m.role for m in memberships}

        workspaces = self.db.scalars(
            select(Workspace).where(Workspace.id.in_(wks_ids)).order_by(Workspace.created_at.desc())
        ).all()

        # Count members per workspace
        counts = dict(
            self.db.execute(
                select(WorkspaceMember.workspace_id, func.count(WorkspaceMember.id))
                .where(WorkspaceMember.workspace_id.in_(wks_ids))
                .group_by(WorkspaceMember.workspace_id)
            ).all()
        )

        return [
            WorkspaceRead(
                id=w.id,
                name=w.name,
                slug=w.slug,
                description=w.description,
                created_at=w.created_at,
                current_user_role=role_by_wks.get(w.id),
                member_count=counts.get(w.id, 1),
            )
            for w in workspaces
        ]

    def get_workspace_or_404(self, workspace_id: str) -> Workspace:
        workspace = self.db.get(Workspace, workspace_id)
        if not workspace:
            raise NotFoundError(f"Workspace {workspace_id} not found")
        return workspace

    def get_membership(self, workspace_id: str, user_id: str) -> WorkspaceMember | None:
        return self.db.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )

    def update_workspace(self, workspace: Workspace, payload: WorkspaceUpdateRequest) -> Workspace:
        if payload.name is not None:
            workspace.name = payload.name.strip()
        if payload.description is not None:
            workspace.description = payload.description.strip() or None
        self.db.commit()
        self.db.refresh(workspace)
        return workspace

    def delete_workspace(self, workspace: Workspace) -> None:
        if workspace.id == "wks_default":
            raise ValidationError("The default workspace cannot be deleted")

        # Deleting the workspace cascades to members and provider keys
        self.db.delete(workspace)
        self.db.commit()

    # --- Workspace Members ----------------------------------------------------

    def list_members(self, workspace_id: str) -> list[WorkspaceMemberRead]:
        rows = self.db.execute(
            select(WorkspaceMember, User)
            .join(User, WorkspaceMember.user_id == User.id)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .order_by(WorkspaceMember.created_at.asc())
        ).all()

        results: list[WorkspaceMemberRead] = []
        for member, user in rows:
            results.append(
                WorkspaceMemberRead(
                    id=member.id,
                    workspace_id=member.workspace_id,
                    user_id=member.user_id,
                    role=member.role,
                    email=user.email,
                    full_name=user.full_name,
                    created_at=member.created_at,
                )
            )
        return results

    def add_or_invite_member(
        self,
        workspace_id: str,
        payload: WorkspaceMemberInviteRequest,
    ) -> WorkspaceMemberRead:
        user = self.db.scalar(select(User).where(User.email == payload.email.lower()))
        if not user:
            raise NotFoundError(
                f"No registered user found with email '{payload.email}'. "
                "The user must register an account first."
            )

        existing = self.get_membership(workspace_id, user.id)
        if existing:
            raise ConflictError(f"User '{payload.email}' is already a member of this workspace")

        membership = WorkspaceMember(
            id=new_id("wkm"),
            workspace_id=workspace_id,
            user_id=user.id,
            role=payload.role,
        )
        self.db.add(membership)
        self.db.commit()
        self.db.refresh(membership)

        return WorkspaceMemberRead(
            id=membership.id,
            workspace_id=membership.workspace_id,
            user_id=membership.user_id,
            role=membership.role,
            email=user.email,
            full_name=user.full_name,
            created_at=membership.created_at,
        )

    def update_member_role(
        self,
        workspace_id: str,
        target_user_id: str,
        payload: WorkspaceMemberUpdateRequest,
    ) -> WorkspaceMemberRead:
        membership = self.get_membership(workspace_id, target_user_id)
        if not membership:
            raise NotFoundError(f"Member {target_user_id} not found in workspace {workspace_id}")

        if membership.role == "owner" and payload.role != "owner":
            owner_count = self.db.scalar(
                select(func.count(WorkspaceMember.id)).where(
                    WorkspaceMember.workspace_id == workspace_id,
                    WorkspaceMember.role == "owner",
                )
            )
            if (owner_count or 0) <= 1:
                raise ValidationError("Cannot demote the last owner of the workspace")

        membership.role = payload.role
        self.db.commit()
        self.db.refresh(membership)

        user = self.db.get(User, target_user_id)
        return WorkspaceMemberRead(
            id=membership.id,
            workspace_id=membership.workspace_id,
            user_id=membership.user_id,
            role=membership.role,
            email=user.email if user else None,
            full_name=user.full_name if user else None,
            created_at=membership.created_at,
        )

    def remove_member(
        self,
        workspace_id: str,
        target_user_id: str,
    ) -> None:
        membership = self.get_membership(workspace_id, target_user_id)
        if not membership:
            raise NotFoundError(f"Member {target_user_id} not found in workspace {workspace_id}")

        if membership.role == "owner":
            owner_count = self.db.scalar(
                select(func.count(WorkspaceMember.id)).where(
                    WorkspaceMember.workspace_id == workspace_id,
                    WorkspaceMember.role == "owner",
                )
            )
            if (owner_count or 0) <= 1:
                raise ValidationError("Cannot remove the last owner of the workspace")

        self.db.delete(membership)
        self.db.commit()

    # --- Provider Keys (Encrypted at Rest) -------------------------------------

    def list_provider_status(self, workspace_id: str) -> list[WorkspaceProviderStatusRead]:
        workspace_keys = {
            k.provider: k
            for k in self.db.scalars(
                select(WorkspaceProviderKey).where(
                    WorkspaceProviderKey.workspace_id == workspace_id
                )
            ).all()
        }

        statuses: list[WorkspaceProviderStatusRead] = []
        for provider in SUPPORTED_PROVIDERS:
            wks_key = workspace_keys.get(provider)
            env_attr = ENV_KEY_MAP.get(provider)
            env_has_key = bool(getattr(settings, env_attr, None)) if env_attr else False

            has_custom_key = wks_key is not None
            is_configured = has_custom_key or env_has_key
            masked = wks_key.key_suffix if wks_key else None
            source = "workspace" if has_custom_key else ("env" if env_has_key else "none")

            statuses.append(
                WorkspaceProviderStatusRead(
                    provider=provider,
                    display_name=PROVIDER_DISPLAY_NAMES.get(provider, provider.title()),
                    is_configured=is_configured,
                    has_workspace_key=has_custom_key,
                    masked_suffix=masked,
                    source=source,
                    created_at=wks_key.created_at if wks_key else None,
                )
            )
        return statuses

    def set_provider_key(
        self,
        workspace_id: str,
        provider: str,
        api_key: str,
    ) -> WorkspaceProviderStatusRead:
        provider_clean = provider.strip().lower()
        key_clean = api_key.strip()
        if not key_clean:
            raise ValidationError("API key cannot be empty")

        encrypted = encrypt_secret(key_clean)
        masked = mask_secret(key_clean)

        existing = self.db.scalar(
            select(WorkspaceProviderKey).where(
                WorkspaceProviderKey.workspace_id == workspace_id,
                WorkspaceProviderKey.provider == provider_clean,
            )
        )

        if existing:
            existing.encrypted_key = encrypted
            existing.key_suffix = masked
            self.db.commit()
            self.db.refresh(existing)
            created_at = existing.created_at
        else:
            new_key = WorkspaceProviderKey(
                id=new_id("wpk"),
                workspace_id=workspace_id,
                provider=provider_clean,
                encrypted_key=encrypted,
                key_suffix=masked,
            )
            self.db.add(new_key)
            self.db.commit()
            self.db.refresh(new_key)
            created_at = new_key.created_at

        return WorkspaceProviderStatusRead(
            provider=provider_clean,
            display_name=PROVIDER_DISPLAY_NAMES.get(provider_clean, provider_clean.title()),
            is_configured=True,
            has_workspace_key=True,
            masked_suffix=masked,
            source="workspace",
            created_at=created_at,
        )

    def delete_provider_key(self, workspace_id: str, provider: str) -> None:
        provider_clean = provider.strip().lower()
        existing = self.db.scalar(
            select(WorkspaceProviderKey).where(
                WorkspaceProviderKey.workspace_id == workspace_id,
                WorkspaceProviderKey.provider == provider_clean,
            )
        )
        if not existing:
            raise NotFoundError(f"No custom provider key configured for '{provider_clean}'")

        self.db.delete(existing)
        self.db.commit()

    def get_effective_provider_key(self, workspace_id: str | None, provider: str) -> str | None:
        """Returns the decrypted workspace API key if set; otherwise falls back to environment settings."""
        provider_clean = provider.strip().lower()
        if workspace_id:
            record = self.db.scalar(
                select(WorkspaceProviderKey).where(
                    WorkspaceProviderKey.workspace_id == workspace_id,
                    WorkspaceProviderKey.provider == provider_clean,
                )
            )
            if record and record.encrypted_key:
                try:
                    return decrypt_secret(record.encrypted_key)
                except Exception as exc:
                    logger.error(f"Failed to decrypt workspace provider key for {provider}: {exc}")

        # Fallback to global environment settings
        env_attr = ENV_KEY_MAP.get(provider_clean)
        if env_attr:
            val = getattr(settings, env_attr, None)
            if val:
                return str(val)
        return None

    def get_effective_provider(self, workspace_id: str | None, provider: str):
        """Returns configured provider instance with workspace-effective credentials."""
        from app.providers.registry import get_provider

        effective_key = self.get_effective_provider_key(workspace_id, provider)
        return get_provider(provider, api_key=effective_key)
