"""Local email/password authentication provider."""

import logging
import shutil
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.gateway.auth.models import User
from app.gateway.auth.password import hash_password_async, needs_rehash, verify_password_async
from app.gateway.auth.providers import AuthProvider
from app.gateway.auth.repositories.base import UserRepository
from deerflow.config.paths import get_paths
from deerflow.persistence.feedback.model import FeedbackRow
from deerflow.persistence.models.run_event import RunEventRow
from deerflow.persistence.run.model import RunRow
from deerflow.persistence.thread_meta.model import ThreadMetaRow
from deerflow.persistence.user.model import UserRow

logger = logging.getLogger(__name__)


class LocalAuthProvider(AuthProvider):
    """Email/password authentication provider using local database."""

    def __init__(self, repository: UserRepository, session_factory: async_sessionmaker[AsyncSession] | None = None):
        """Initialize with a UserRepository.

        Args:
            repository: UserRepository implementation (SQLite)
            session_factory: Optional shared session factory for cascade operations
        """
        self._repo = repository
        self._sf = session_factory

    async def authenticate(self, credentials: dict) -> User | None:
        """Authenticate with email and password.

        Args:
            credentials: dict with 'email' and 'password' keys

        Returns:
            User if authentication succeeds, None otherwise
        """
        email = credentials.get("email")
        password = credentials.get("password")

        if not email or not password:
            return None

        user = await self._repo.get_user_by_email(email)
        if user is None:
            return None

        if user.password_hash is None:
            # OAuth user without local password
            return None

        if not await verify_password_async(password, user.password_hash):
            return None

        if needs_rehash(user.password_hash):
            try:
                user.password_hash = await hash_password_async(password)
                await self._repo.update_user(user)
            except Exception:
                # Rehash is an opportunistic upgrade; a transient DB error must not
                # prevent an otherwise-valid login from succeeding.
                logger.warning("Failed to rehash password for user %s; login will still succeed", user.email, exc_info=True)

        return user

    async def get_user(self, user_id: str) -> User | None:
        """Get user by ID."""
        return await self._repo.get_user_by_id(user_id)

    async def create_user(self, email: str, password: str | None = None, system_role: str = "user", needs_setup: bool = False) -> User:
        """Create a new local user.

        Args:
            email: User email address
            password: Plain text password (will be hashed)
            system_role: Role to assign ("admin" or "user")
            needs_setup: If True, user must complete setup on first login

        Returns:
            Created User instance
        """
        password_hash = await hash_password_async(password) if password else None
        user = User(
            email=email,
            password_hash=password_hash,
            system_role=system_role,
            needs_setup=needs_setup,
        )
        return await self._repo.create_user(user)

    async def get_user_by_oauth(self, provider: str, oauth_id: str) -> User | None:
        """Get user by OAuth provider and ID."""
        return await self._repo.get_user_by_oauth(provider, oauth_id)

    async def count_users(self) -> int:
        """Return total number of registered users."""
        return await self._repo.count_users()

    async def count_admin_users(self) -> int:
        """Return number of admin users."""
        return await self._repo.count_admin_users()

    async def update_user(self, user: User) -> User:
        """Update an existing user."""
        return await self._repo.update_user(user)

    async def get_user_by_email(self, email: str) -> User | None:
        """Get user by email."""
        return await self._repo.get_user_by_email(email)

    async def list_all_users(self) -> list[User]:
        """Return all users ordered by creation time descending."""
        return await self._repo.list_all_users()

    async def delete_user(self, user_id: str) -> bool:
        """Delete a user and cascade-clean all associated data.

        Args:
            user_id: User UUID as string

        Returns:
            True if user was found and deleted
        """
        if self._sf is None:
            raise RuntimeError("Session factory required for cascade delete")

        async with self._sf() as session:
            # Verify user exists
            user = await self._repo.get_user_by_id(user_id)
            if user is None:
                return False

            # Cascade delete in dependency order
            await session.execute(delete(FeedbackRow).where(FeedbackRow.user_id == user_id))
            await session.execute(delete(RunEventRow).where(RunEventRow.user_id == user_id))
            await session.execute(delete(RunRow).where(RunRow.user_id == user_id))
            await session.execute(delete(ThreadMetaRow).where(ThreadMetaRow.user_id == user_id))
            await session.execute(delete(UserRow).where(UserRow.id == user_id))
            await session.commit()

        # Clean up filesystem
        user_dir = get_paths().base_dir / "users" / user_id
        if user_dir.exists():
            shutil.rmtree(user_dir)
            logger.info("Removed user directory: %s", user_dir)

        return True
