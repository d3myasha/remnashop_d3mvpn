from typing import Any, Optional, Type, TypeVar, Union, cast

from loguru import logger
from sqlalchemy import ColumnExpressionArgument, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from src.infrastructure.database.models import BaseSQL

T = TypeVar("T", bound=BaseSQL)
ModelType = Type[T]

ConditionType = ColumnExpressionArgument[Any]
OrderByArgument = Union[ColumnExpressionArgument[Any], InstrumentedAttribute[Any]]


class BaseDAO:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_instance(self, instance: T) -> T:
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)

        logger.debug(f"Instance '{instance.__class__.__name__}' created in database")
        return instance

    async def create_instances(self, instances: list[T]) -> list[T]:
        if not instances:
            return []

        self.session.add_all(instances)
        await self.session.flush()
        for instance in instances:
            await self.session.refresh(instance)

        logger.debug(f"Created '{len(instances)}' instances in database")
        return instances

    async def merge_instance(self, instance: T) -> T:
        merged = await self.session.merge(instance)
        logger.debug(f"Instance '{instance.__class__.__name__}' merged")
        return merged

    async def delete_instance(self, instance: T) -> None:
        await self.session.delete(instance)
        logger.debug(f"Instance '{instance.__class__.__name__}' marked for deletion")

    async def _get_one(self, model: ModelType[T], *conditions: ConditionType) -> Optional[T]:
        result = await self.session.execute(select(model).where(*conditions))
        return result.unique().scalar_one_or_none()

    async def _get_many(
        self,
        model: ModelType[T],
        *conditions: ConditionType,
        order_by: Optional[OrderByArgument] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> list[T]:
        query = select(model).where(*conditions)

        if order_by is not None:
            if isinstance(order_by, (list, tuple)):
                query = query.order_by(*order_by)
            else:
                query = query.order_by(order_by)

        if limit is not None:
            query = query.limit(limit)

        if offset is not None:
            query = query.offset(offset)

        result = await self.session.execute(query)
        return list(result.unique().scalars().all())

    async def _update(
        self,
        model: ModelType[T],
        *conditions: ConditionType,
        load_result: bool = True,
        **kwargs: Any,
    ) -> Optional[T]:
        if not kwargs:
            if not load_result:
                return None
            return cast(Optional[T], await self._get_one(model, *conditions))

        query = update(model).where(*conditions).values(**kwargs)

        if load_result:
            query = query.returning(model.id)  # type: ignore [attr-defined]

        result = await self.session.execute(query)
        obj_id: Optional[int] = result.scalar_one_or_none()

        if obj_id is not None and load_result:
            db_obj = await self.session.get(model, obj_id)
            if db_obj:
                await self.session.refresh(db_obj)
                logger.debug(f"Updated '{model.__name__}' with ID '{obj_id}'")
            return db_obj

        return None

    async def _delete(self, model: ModelType[T], *conditions: ConditionType) -> int:
        result = await self.session.execute(delete(model).where(*conditions))
        count = result.rowcount  # type: ignore[attr-defined]
        logger.debug(f"Deleted '{count}' rows from '{model.__name__}'")
        return cast(int, count)

    async def _count(self, model: Type[T], *conditions: ConditionType) -> int:
        query = select(func.count()).select_from(model).where(*conditions)
        result = await self.session.scalar(query)
        return result or 0
