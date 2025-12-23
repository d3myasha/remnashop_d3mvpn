from collections.abc import AsyncIterable

from dishka import Provider, Scope, provide
from loguru import logger
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import AppConfig
from src.infrastructure.database import UnitOfWork


class DatabaseProvider(Provider):
    scope = Scope.APP

    @provide
    async def engine(self, config: AppConfig) -> AsyncIterable[AsyncEngine]:
        logger.debug("Creating AsyncEngine")
        engine = create_async_engine(
            url=config.database.dsn,
            echo=config.database.echo,
            echo_pool=config.database.echo_pool,
            pool_size=config.database.pool_size,
            max_overflow=config.database.max_overflow,
            pool_timeout=config.database.pool_timeout,
            pool_recycle=config.database.pool_recycle,
        )
        yield engine
        logger.debug("Disposing AsyncEngine")
        await engine.dispose()

    @provide
    def session_maker(self, engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
        session_maker = async_sessionmaker(bind=engine, expire_on_commit=False)
        logger.debug("Created session maker")
        return session_maker

    @provide(scope=Scope.REQUEST)
    async def provide_session(
        self, pool: async_sessionmaker[AsyncSession]
    ) -> AsyncIterable[AsyncSession]:
        logger.debug(f"Attempting to get session from pool for request")

        async with pool() as session:
            logger.debug(f"Session obtained from pool")
            yield session
        logger.debug(f"Session returned to pool")

    uow = provide(source=UnitOfWork, scope=Scope.REQUEST)
