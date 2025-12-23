from typing import Any, Optional

from loguru import logger
from sqlalchemy import cast, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.dto import UserDTO
from src.application.protocols import UserDAO
from src.core.enums import UserRole
from src.infrastructure.database.models import User


class UserDAOImpl(UserDAO):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, user_dto: UserDTO) -> UserDTO:
        user = User(**user_dto.model_dump())
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)

        logger.info(f"New user '{user.telegram_id}' created in SQL database")
        return UserDTO.model_validate(user)

    async def get(self, telegram_id: int) -> Optional[UserDTO]:
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await self.session.execute(stmt)
        user = result.unique().scalar_one_or_none()

        if user:
            logger.debug(f"User '{telegram_id}' found in database")
            return UserDTO.model_validate(user)

        logger.debug(f"User '{telegram_id}' not found")
        return None

    async def get_by_ids(self, telegram_ids: list[int]) -> list[UserDTO]:
        stmt = select(User).where(User.telegram_id.in_(telegram_ids))
        result = await self.session.execute(stmt)
        users = result.unique().scalars().all()

        logger.debug(f"Retrieved '{len(users)}' users by ID list")
        return [UserDTO.model_validate(u) for u in users]

    async def get_by_partial_name(self, query: str) -> list[UserDTO]:
        search_pattern = f"%{query.lower()}%"
        stmt = select(User).where(
            or_(
                func.lower(User.name).like(search_pattern),
                func.lower(User.username).like(search_pattern),
            )
        )
        result = await self.session.execute(stmt)
        users = result.unique().scalars().all()

        logger.debug(f"Found '{len(users)}' users matching query '{query}'")
        return [UserDTO.model_validate(u) for u in users]

    async def update(self, telegram_id: int, **data: Any) -> Optional[UserDTO]:
        if not data:
            return await self.get(telegram_id)

        stmt = update(User).where(User.telegram_id == telegram_id).values(**data).returning(User)
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()

        if user:
            logger.info(f"User '{telegram_id}' updated successfully with data '{data}'")
            return UserDTO.model_validate(user)

        return None

    async def delete(self, telegram_id: int) -> bool:
        stmt = delete(User).where(User.telegram_id == telegram_id)
        result = await self.session.execute(stmt)

        if cast(int, result.rowcount) > 0:  # type: ignore[attr-defined]
            logger.info(f"User '{telegram_id}' deleted from database")
            return True

        return False

    async def count(self) -> int:
        stmt = select(func.count()).select_from(User)
        total = await self.session.scalar(stmt) or 0

        logger.debug(f"Total users count requested: '{total}'")
        return total

    async def filter_by_role(self, role: UserRole) -> list[UserDTO]:
        stmt = select(User).where(User.role == role)
        result = await self.session.execute(stmt)
        users = result.unique().scalars().all()

        logger.debug(f"Filtered '{len(users)}' users with role '{role}'")
        return [UserDTO.model_validate(u) for u in users]
