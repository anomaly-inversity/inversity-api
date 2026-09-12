"""Database seeder: workspace demo + 3 user demo.

Usage:
    uv run python -m app.database.seed
    # atau
    python -m app.database.seed

Idempotent: aman dijalankan berulang (upsert by email / workspace name).
"""

import asyncio
import secrets
import sys

from sqlalchemy import select

from app.core.logger import logger
from app.database.models import RoleEnum, User, Workspace, WorkspaceUser
from app.database.session import AsyncSessionLocal, engine
from app.modules.auth.utils import get_password_hash

WORKSPACE_NAME = "Inversity Inc"

# (email, name, workspace_role)
SEED_USERS: list[tuple[str, str, RoleEnum]] = [
    ("admin@demo.com", "Admin Demo", RoleEnum.ADMIN),
    ("student@demo.com", "Student Demo", RoleEnum.USER),
    ("teacher@demo.com", "Teacher Demo", RoleEnum.REVIEWER),
]


def _password_for(email: str) -> str:
    """Password = prefiks sebelum @. cth: student@demo.com -> student."""
    return email.split("@")[0]


async def _get_or_create_workspace(db, admin_user_id) -> Workspace:
    stmt = select(Workspace).where(Workspace.name == WORKSPACE_NAME)
    workspace = (await db.execute(stmt)).scalar_one_or_none()
    if workspace is not None:
        return workspace

    for _ in range(5):
        code = secrets.token_urlsafe(8)
        exists = (
            await db.execute(select(Workspace.id).where(Workspace.invite_code == code))
        ).scalar_one_or_none()
        if exists is None:
            break
    else:
        code = secrets.token_urlsafe(16)

    workspace = Workspace(
        name=WORKSPACE_NAME,
        invite_code=code,
        created_by=admin_user_id,
    )
    db.add(workspace)
    await db.flush()
    return workspace


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        users: dict[str, User] = {}

        # 1. Upsert users
        for email, name, _role in SEED_USERS:
            stmt = select(User).where(User.email == email)
            user = (await db.execute(stmt)).scalar_one_or_none()
            password = _password_for(email)
            if user is None:
                user = User(
                    email=email,
                    name=name,
                    password_hash=get_password_hash(password),
                )
                db.add(user)
                await db.flush()
                logger.info("seed_user_created", email=email)
            else:
                # Pastikan password sesuai konvensi seeder.
                user.password_hash = get_password_hash(password)
                user.name = name
                logger.info("seed_user_exists", email=email)
            users[email] = user

        await db.flush()
        admin_user = users["admin@demo.com"]

        # 2. Get or create workspace (created_by = admin)
        workspace = await _get_or_create_workspace(db, admin_user.id)
        if workspace.created_by is None:
            workspace.created_by = admin_user.id
        await db.flush()

        # 3. Upsert memberships
        for email, _name, role in SEED_USERS:
            user = users[email]
            stmt = select(WorkspaceUser).where(
                WorkspaceUser.workspace_id == workspace.id,
                WorkspaceUser.user_id == user.id,
            )
            membership = (await db.execute(stmt)).scalar_one_or_none()
            if membership is None:
                membership = WorkspaceUser(
                    workspace_id=workspace.id,
                    user_id=user.id,
                    role=role,
                )
                db.add(membership)
                logger.info("seed_membership_created", email=email, role=role.value)
            elif membership.role != role:
                membership.role = role
                logger.info("seed_membership_updated", email=email, role=role.value)

        await db.commit()

        print(f"Workspace: {workspace.name} (invite_code={workspace.invite_code})")
        for email, _name, role in SEED_USERS:
            print(f"  - {email} / password={_password_for(email)} / role={role.value}")


async def main() -> int:
    try:
        await seed()
    except Exception as e:
        logger.error("seed_failed", error=str(e))
        print(f"Seed gagal: {e}", file=sys.stderr)
        return 1
    finally:
        await engine.dispose()
    logger.info("seed_success")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
