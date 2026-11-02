"""Pydantic schemas for authentication, users, workspaces, and workspace provider keys."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

EmailType = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        pattern=r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$",
        max_length=255,
    ),
]


# --- Auth & User Schemas -----------------------------------------------------


class UserRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailType
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=160)


class UserLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailType
    password: str


class RefreshTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str | None = None
    is_active: bool
    is_superuser: bool
    created_at: datetime


# --- Workspace Schemas -------------------------------------------------------


class WorkspaceCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    slug: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=2000)


class WorkspaceUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)


class WorkspaceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    description: str | None = None
    created_at: datetime
    current_user_role: str | None = None
    member_count: int = 1


class WorkspaceMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    user_id: str
    role: Literal["owner", "editor", "viewer"]
    email: str | None = None
    full_name: str | None = None
    created_at: datetime


class WorkspaceMemberInviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailType
    role: Literal["owner", "editor", "viewer"] = "editor"


class WorkspaceMemberUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["owner", "editor", "viewer"]


class UserWithWorkspaces(BaseModel):
    user: UserRead
    workspaces: list[WorkspaceRead] = Field(default_factory=list)
    active_workspace_id: str | None = None


# --- Workspace Provider Keys -------------------------------------------------


class WorkspaceProviderKeySetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: str = Field(min_length=1, max_length=512)


class WorkspaceProviderStatusRead(BaseModel):
    provider: str
    display_name: str = ""
    is_configured: bool = False
    has_workspace_key: bool = False
    masked_suffix: str | None = None
    source: Literal["workspace", "env", "none"] = "none"
    created_at: datetime | None = None
