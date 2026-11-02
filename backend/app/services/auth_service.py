"""Authentication and user session management service."""

from __future__ import annotations

import re
from datetime import UTC, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    RateLimitExceededError,
    ValidationFailedError,
)
from app.core.logging import get_logger
from app.core.security import (
    DUMMY_BCRYPT_HASH,
    auth_limiter,
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    validate_password_strength,
    verify_password,
)
from app.db.base import new_id, utcnow
from app.models.auth import RefreshToken, User, Workspace, WorkspaceMember
from app.schemas.auth import TokenResponse

logger = get_logger(__name__)


def slugify(text: str) -> str:
    """Generate a clean URL slug from text."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-") or "workspace"


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def register(
        self,
        email: str,
        password: str,
        full_name: str | None = None,
        workspace_name: str | None = None,
    ) -> tuple[User, TokenResponse]:
        """Register a new user, create an initial workspace, and issue session tokens."""
        clean_email = email.strip().lower()

        # 1. Password complexity validation
        valid, reason = validate_password_strength(password)
        if not valid:
            raise ValidationFailedError(reason or "Password does not meet complexity requirements.")

        # 2. Check for duplicate email
        existing = self.db.execute(
            select(User).where(User.email == clean_email)
        ).scalar_one_or_none()
        if existing:
            raise ConflictError("An account with this email already exists.")

        # 3. Create User
        user = User(
            id=new_id("usr"),
            email=clean_email,
            hashed_password=hash_password(password),
            full_name=full_name.strip() if full_name else None,
            is_active=True,
            is_superuser=False,
        )
        self.db.add(user)
        self.db.flush()

        # 4. Create primary workspace for new user
        ws_name = (
            workspace_name.strip()
            if workspace_name
            else f"{(full_name or clean_email.split('@')[0])}'s Workspace"
        )
        base_slug = slugify(ws_name)
        # Ensure slug uniqueness
        slug = base_slug
        count = 1
        while self.db.execute(select(Workspace).where(Workspace.slug == slug)).scalar_one_or_none():
            slug = f"{base_slug}-{count}"
            count += 1

        workspace = Workspace(
            id=new_id("wks"),
            name=ws_name,
            slug=slug,
            description=f"Personal workspace for {clean_email}.",
        )
        self.db.add(workspace)
        self.db.flush()

        # 5. Add user as workspace owner
        membership = WorkspaceMember(
            id=new_id("wkm"),
            workspace_id=workspace.id,
            user_id=user.id,
            role="owner",
        )
        self.db.add(membership)

        # 6. Issue tokens
        token_resp = self._issue_session_tokens(user, workspace_id=workspace.id)

        from app.services.audit_log_service import AuditLogService
        AuditLogService.log(
            self.db,
            workspace_id=workspace.id,
            user_id=user.id,
            actor_email=user.email,
            action="auth.register",
            resource_type="user",
            resource_id=user.id,
        )

        self.db.commit()
        self.db.refresh(user)

        logger.info("registered new user %s (workspace=%s)", user.id, workspace.id)
        return user, token_resp

    def login(self, email: str, password: str, client_ip: str = "unknown") -> tuple[User, TokenResponse]:
        """Authenticate user with email and password in constant time."""
        clean_email = email.strip().lower()

        # Rate limiting on email and IP
        rate_key = f"{client_ip}:{clean_email}"
        if not auth_limiter.is_allowed(rate_key):
            raise RateLimitExceededError("Too many login attempts. Please try again later.")

        user = self.db.execute(
            select(User).where(User.email == clean_email)
        ).scalar_one_or_none()

        from app.services.audit_log_service import AuditLogService

        # Always verify password (or dummy hash) to eliminate timing channel
        if not user or not user.is_active:
            verify_password(password, DUMMY_BCRYPT_HASH)
            AuditLogService.log(
                self.db,
                workspace_id="wks_default",
                actor_email=clean_email,
                action="auth.login",
                resource_type="user",
                ip_address=client_ip,
                status="failure",
                details={"reason": "invalid_credentials"},
            )
            self.db.commit()
            raise AuthenticationError("Invalid email or password.")

        if not verify_password(password, user.hashed_password):
            AuditLogService.log(
                self.db,
                workspace_id="wks_default",
                actor_email=clean_email,
                user_id=user.id,
                action="auth.login",
                resource_type="user",
                resource_id=user.id,
                ip_address=client_ip,
                status="failure",
                details={"reason": "invalid_credentials"},
            )
            self.db.commit()
            raise AuthenticationError("Invalid email or password.")

        # Reset rate limit counter on success
        auth_limiter.reset(rate_key)

        # Resolve primary workspace for the token
        primary_wks = self._resolve_primary_workspace_id(user.id)
        token_resp = self._issue_session_tokens(user, workspace_id=primary_wks)

        AuditLogService.log(
            self.db,
            workspace_id=primary_wks or "wks_default",
            user_id=user.id,
            actor_email=user.email,
            action="auth.login",
            resource_type="user",
            resource_id=user.id,
            ip_address=client_ip,
            status="success",
        )
        self.db.commit()

        logger.info("user %s logged in successfully", user.id)
        return user, token_resp

    def refresh(self, refresh_token_str: str) -> TokenResponse:
        """Rotate an active refresh token and issue a fresh access token."""
        h = hash_token(refresh_token_str)
        token_rec = self.db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == h)
        ).scalar_one_or_none()

        if not token_rec:
            raise AuthenticationError("Invalid or expired refresh token.")

        # Replay / reuse detection: If already revoked, revoke all tokens for this user
        if token_rec.revoked:
            logger.warning("revoked refresh token reuse detected for user %s", token_rec.user_id)
            self.db.execute(
                update(RefreshToken)
                .where(RefreshToken.user_id == token_rec.user_id)
                .values(revoked=True)
            )
            self.db.commit()
            raise AuthenticationError("Revoked refresh token reuse detected. All sessions revoked.")

        now = utcnow()
        expires_at = token_rec.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at < now:
            token_rec.revoked = True
            self.db.commit()
            raise AuthenticationError("Refresh token has expired. Please log in again.")

        user = self.db.get(User, token_rec.user_id)
        if not user or not user.is_active:
            raise AuthenticationError("User account is inactive or disabled.")

        # Invalidate current token and rotate to a new one
        new_token_str = generate_refresh_token()
        new_hash = hash_token(new_token_str)

        token_rec.revoked = True
        token_rec.replaced_by = new_hash

        refresh_expires = now + timedelta(days=settings.refresh_token_expire_days)
        new_token_rec = RefreshToken(
            id=new_id("rft"),
            user_id=user.id,
            token_hash=new_hash,
            expires_at=refresh_expires,
            revoked=False,
        )
        self.db.add(new_token_rec)

        # Issue fresh access token
        primary_wks = self._resolve_primary_workspace_id(user.id)
        access_token = create_access_token(
            user_id=user.id,
            email=user.email,
            workspace_id=primary_wks,
        )
        self.db.commit()

        return TokenResponse(
            access_token=access_token,
            refresh_token=new_token_str,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
        )

    def logout(self, refresh_token_str: str | None) -> None:
        """Revoke a refresh token on logout."""
        if not refresh_token_str:
            return
        from app.services.audit_log_service import AuditLogService

        h = hash_token(refresh_token_str)
        token_rec = self.db.execute(
            select(RefreshToken).where(RefreshToken.token_hash == h)
        ).scalar_one_or_none()
        if token_rec:
            token_rec.revoked = True
            AuditLogService.log(
                self.db,
                workspace_id="wks_default",
                user_id=token_rec.user_id,
                action="auth.logout",
                resource_type="user",
                resource_id=token_rec.user_id,
            )
        self.db.commit()

    def get_user_profile_and_workspaces(self, user: User) -> dict[str, Any]:
        """Fetch user profile with associated workspaces and membership roles."""
        memberships = (
            self.db.execute(
                select(WorkspaceMember, Workspace)
                .join(Workspace, WorkspaceMember.workspace_id == Workspace.id)
                .where(WorkspaceMember.user_id == user.id)
                .order_by(Workspace.created_at)
            )
            .all()
        )

        ws_list: list[dict[str, Any]] = []
        for member, ws in memberships:
            # Count members in workspace
            member_count = (
                self.db.execute(
                    select(WorkspaceMember).where(WorkspaceMember.workspace_id == ws.id)
                )
                .scalars()
                .all()
            )
            ws_list.append(
                {
                    "id": ws.id,
                    "name": ws.name,
                    "slug": ws.slug,
                    "description": ws.description,
                    "created_at": ws.created_at,
                    "current_user_role": member.role,
                    "member_count": len(member_count),
                }
            )

        active_ws_id = ws_list[0]["id"] if ws_list else None
        return {
            "user": user,
            "workspaces": ws_list,
            "active_workspace_id": active_ws_id,
        }

    # -- Internal Helpers -----------------------------------------------------

    def _issue_session_tokens(self, user: User, workspace_id: str | None) -> TokenResponse:
        """Helper to create matching access and refresh tokens."""
        now = utcnow()
        refresh_expires = now + timedelta(days=settings.refresh_token_expire_days)
        raw_refresh = generate_refresh_token()

        refresh_rec = RefreshToken(
            id=new_id("rft"),
            user_id=user.id,
            token_hash=hash_token(raw_refresh),
            expires_at=refresh_expires,
            revoked=False,
        )
        self.db.add(refresh_rec)

        access_token = create_access_token(
            user_id=user.id,
            email=user.email,
            workspace_id=workspace_id,
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
        )

    def _resolve_primary_workspace_id(self, user_id: str) -> str | None:
        """Resolve the first workspace the user belongs to."""
        member = (
            self.db.execute(
                select(WorkspaceMember)
                .where(WorkspaceMember.user_id == user_id)
                .order_by(WorkspaceMember.created_at)
            )
            .scalars()
            .first()
        )
        return member.workspace_id if member else None
