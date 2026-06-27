"""Setup wizard request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.library import LibraryCreate


class SetupAdmin(BaseModel):
    """Admin account created during first-run setup."""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(
        ...,
        min_length=3,
        max_length=32,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="URL-safe username, 3-32 chars.",
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Admin password (min 8 chars).",
    )


class SetupPayload(BaseModel):
    """Body for ``POST /api/setup``."""

    model_config = ConfigDict(extra="forbid")

    admin: SetupAdmin
    libraries: list[LibraryCreate] = Field(
        default_factory=list,
        description="Initial manga folders. Must point to mounted directories.",
    )
    settings: dict[str, object] | None = Field(
        default=None,
        description="Optional runtime settings overrides (merged with defaults).",
    )


class SetupStatus(BaseModel):
    """Response for ``GET /api/setup/status``."""

    model_config = ConfigDict(from_attributes=True)

    setup_required: bool
    has_users: bool
    has_libraries: bool
    default_settings: dict[str, object]
