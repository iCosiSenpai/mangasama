"""``/api/setup`` — first-run wizard endpoints (public until setup completes)."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.core import setup_state
from app.deps import DBSession
from app.schemas.setup import SetupPayload, SetupStatus
from app.services import library as library_service

router = APIRouter(tags=["setup"])


@router.get("/setup/status", response_model=SetupStatus)
async def setup_status(session: DBSession) -> SetupStatus:
    """Tell the frontend whether the first-run wizard must be shown.

    Always public; it is needed before the admin account exists.
    """
    libs = await library_service.list_libraries(session)
    completed = setup_state.is_setup_completed()
    return SetupStatus(
        setup_required=not completed,
        has_users=completed,
        has_libraries=len(libs) > 0,
        default_settings=setup_state.DEFAULT_RUNTIME_SETTINGS,
    )


@router.post("/setup", status_code=status.HTTP_201_CREATED)
async def complete_setup(payload: SetupPayload, session: DBSession) -> dict[str, object]:
    """Finish initial setup: create admin, seed settings, create first libraries.

    Can only be called once. If library creation fails after the admin file is
    written, the setup is considered completed; the user can add libraries from
    the regular UI.
    """
    if setup_state.is_setup_completed():
        raise ValueError("setup already completed")

    # Validate credentials before touching disk.
    setup_state.validate_username(payload.admin.username)
    setup_state.validate_password(payload.admin.password)

    # Write admin account and runtime settings first.
    setup_state.write_admin(payload.admin.username, payload.admin.password)
    merged = setup_state.init_runtime_settings(payload.settings or {})

    # Create the initial libraries inside the same request transaction.
    created: list[dict] = []
    for lib in payload.libraries:
        lib_obj = await library_service.create_library(session, lib)
        created.append({"id": lib_obj.id, "name": lib_obj.name})

    await session.commit()

    return {
        "setup": "ok",
        "username": payload.admin.username,
        "libraries": len(created),
        "library_ids": [c["id"] for c in created],
        "settings": merged,
    }
