"""Admin-only endpoints for user management."""

from __future__ import annotations

import secrets
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr

from app.gateway.auth.config import get_auth_config
from app.gateway.auth.local_provider import LocalAuthProvider
from app.gateway.auth.password import hash_password
from app.gateway.deps import get_current_user_from_request, get_local_provider
from deerflow.persistence.engine import get_session_factory
from deerflow.persistence.invite_code.model import InviteCodeRow
from deerflow.persistence.run.model import RunRow
from deerflow.persistence.thread_meta.model import ThreadMetaRow
from sqlalchemy import func, select, text

router = APIRouter(prefix="/api/admin", tags=["admin"])


class UpdateStatusBody(BaseModel):
    is_active: bool


class UpdateRoleBody(BaseModel):
    system_role: str


class CreateUserBody(BaseModel):
    email: EmailStr
    password: str
    system_role: str = "user"


async def require_admin(
    request: Request,
    user=Depends(get_current_user_from_request),
) -> None:
    """FastAPI dependency: raise 403 if current user is not admin."""
    if user.system_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="您没有管理员权限",
        )


@router.get("/users")
async def list_users(
    request: Request,
    _: None = Depends(require_admin),
) -> list[dict]:
    """List all registered users (admin only)."""
    provider: LocalAuthProvider = get_local_provider()
    users = await provider.list_all_users()

    return [
        {
            "id": str(u.id),
            "email": u.email,
            "role": u.system_role,
            "createdAt": u.created_at.isoformat() if u.created_at else None,
            "isActive": u.is_active,
        }
        for u in users
    ]


@router.patch("/users/{user_id}/status")
async def update_user_status(
    user_id: str,
    body: UpdateStatusBody,
    _: None = Depends(require_admin),
) -> dict:
    """Enable or disable a user account."""
    provider: LocalAuthProvider = get_local_provider()
    user = await provider.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = body.is_active
    await provider.update_user(user)

    return {"id": str(user.id), "isActive": user.is_active}


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: str,
    _: None = Depends(require_admin),
) -> dict:
    """Reset a user's password and return the new plaintext password."""
    provider: LocalAuthProvider = get_local_provider()
    user = await provider.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    new_password = secrets.token_urlsafe(12)
    user.password_hash = hash_password(new_password)
    user.token_version += 1  # invalidate existing JWTs
    await provider.update_user(user)

    return {"id": str(user.id), "password": new_password}


@router.post("/users")
async def create_user(
    body: CreateUserBody,
    _: None = Depends(require_admin),
) -> dict:
    """Create a new user (admin only)."""
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    provider: LocalAuthProvider = get_local_provider()
    try:
        user = await provider.create_user(
            email=str(body.email),
            password=body.password,
            system_role=body.system_role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "id": str(user.id),
        "email": user.email,
        "role": user.system_role,
        "createdAt": user.created_at.isoformat() if user.created_at else None,
    }


@router.patch("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    body: UpdateRoleBody,
    _: None = Depends(require_admin),
) -> dict:
    """Change a user's role (admin/user)."""
    if body.system_role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="Invalid role")

    provider: LocalAuthProvider = get_local_provider()
    user = await provider.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent downgrading the last admin
    if user.system_role == "admin" and body.system_role == "user":
        admin_count = await provider.count_admin_users()
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot downgrade the last admin")

    user.system_role = body.system_role  # type: ignore[assignment]
    await provider.update_user(user)

    return {"id": str(user.id), "role": user.system_role}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    request: Request,
    _: None = Depends(require_admin),
) -> dict:
    """Delete a user and cascade-clean all associated data."""
    current_user = request.state.user
    if str(current_user.id) == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    provider: LocalAuthProvider = get_local_provider()
    target = await provider.get_user(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent deleting the last admin
    if target.system_role == "admin":
        admin_count = await provider.count_admin_users()
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot delete the last admin")

    # Cascade delete via provider (handles DB rows + filesystem)
    await provider.delete_user(user_id)

    return {"deleted": True}


@router.get("/settings")
async def get_settings(
    _: None = Depends(require_admin),
) -> dict:
    """Get system settings."""
    cfg = get_auth_config()
    return {"allowPublicRegistration": cfg.allow_public_registration}


class SettingsBody(BaseModel):
    allow_public_registration: bool


@router.put("/settings")
async def update_settings(
    body: SettingsBody,
    _: None = Depends(require_admin),
) -> dict:
    """Update system settings."""
    from app.gateway.auth.config import set_auth_config

    cfg = get_auth_config()
    cfg.allow_public_registration = body.allow_public_registration
    set_auth_config(cfg)
    return {"allowPublicRegistration": cfg.allow_public_registration}


@router.get("/invite-codes")
async def list_invite_codes(
    _: None = Depends(require_admin),
) -> list[dict]:
    """List all invite codes."""
    sf = get_session_factory()
    if sf is None:
        return []
    async with sf() as session:
        result = await session.execute(select(InviteCodeRow).order_by(InviteCodeRow.created_at.desc()))
        rows = result.scalars().all()
        return [
            {
                "code": r.code,
                "createdBy": r.created_by,
                "createdAt": r.created_at.isoformat() if r.created_at else None,
                "maxUses": r.max_uses,
                "usedCount": r.used_count,
                "isActive": r.is_active,
            }
            for r in rows
        ]


class CreateInviteCodeBody(BaseModel):
    max_uses: int = 1


@router.post("/invite-codes")
async def create_invite_code(
    request: Request,
    body: CreateInviteCodeBody,
    _: None = Depends(require_admin),
) -> dict:
    """Create a new invite code."""
    code = secrets.token_urlsafe(16)
    sf = get_session_factory()
    if sf is None:
        raise HTTPException(status_code=500, detail="Database not available")
    current_user = request.state.user
    row = InviteCodeRow(
        code=code,
        created_by=str(current_user.id),
        max_uses=body.max_uses,
    )
    async with sf() as session:
        session.add(row)
        await session.commit()
    return {"code": code, "maxUses": body.max_uses}


@router.delete("/invite-codes/{code}")
async def delete_invite_code(
    code: str,
    _: None = Depends(require_admin),
) -> dict:
    """Delete (deactivate) an invite code."""
    sf = get_session_factory()
    if sf is None:
        raise HTTPException(status_code=500, detail="Database not available")
    async with sf() as session:
        result = await session.execute(select(InviteCodeRow).where(InviteCodeRow.code == code))
        row = result.scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Invite code not found")
        row.is_active = False
        await session.commit()
    return {"deleted": True}


@router.get("/stats")
async def get_stats(
    _: None = Depends(require_admin),
) -> dict:
    """Return system-wide statistics for the admin dashboard."""
    provider: LocalAuthProvider = get_local_provider()
    sf = get_session_factory()

    total_users = await provider.count_users()
    total_admins = await provider.count_admin_users()

    total_threads = 0
    total_runs = 0
    today_new_users = 0
    daily_new_users: list[dict] = []

    if sf is not None:
        async with sf() as session:
            # Total threads
            result = await session.execute(select(func.count()).select_from(ThreadMetaRow))
            total_threads = result.scalar() or 0

            # Total runs
            result = await session.execute(select(func.count()).select_from(RunRow))
            total_runs = result.scalar() or 0

            # Today new users (SQLite compatible)
            result = await session.execute(
                text("SELECT COUNT(*) FROM users WHERE DATE(created_at) = DATE('now')")
            )
            today_new_users = result.scalar() or 0

            # Daily new users for last 30 days
            result = await session.execute(
                text(
                    "SELECT DATE(created_at) as day, COUNT(*) as cnt "
                    "FROM users WHERE created_at >= DATE('now', '-30 days') "
                    "GROUP BY DATE(created_at) ORDER BY day"
                )
            )
            daily_new_users = [
                {"date": row[0], "count": row[1]} for row in result.fetchall()
            ]

    return {
        "totalUsers": total_users,
        "totalAdmins": total_admins,
        "todayNewUsers": today_new_users,
        "totalThreads": total_threads,
        "totalRuns": total_runs,
        "dailyNewUsers": daily_new_users,
    }
