from types import TracebackType
from typing import Optional, Self, Type

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession


class UnitOfWork:
    _active_sessions: int = 0

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def __aenter__(self) -> Self:
        UnitOfWork._active_sessions += 1
        logger.debug(f"SQL session started. Active sessions: '{UnitOfWork._active_sessions}'")
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        try:
            if exc_type:
                await self.rollback()
        finally:
            await self.session.close()
            UnitOfWork._active_sessions -= 1
            logger.debug(f"SQL session closed. Active sessions: '{UnitOfWork._active_sessions}'")

    async def commit(self) -> None:
        await self.session.commit()
        logger.debug("SQL transaction committed successfully")

    async def rollback(self) -> None:
        await self.session.rollback()
        logger.warning("SQL transaction rolled back")
