from typing import Optional, Protocol, runtime_checkable
from uuid import UUID

from src.application.dto import BroadcastDto, BroadcastMessageDto
from src.core.enums import BroadcastMessageStatus, BroadcastStatus


@runtime_checkable
class BroadcastDao(Protocol):
    async def create(self, broadcast: BroadcastDto) -> BroadcastDto: ...

    async def get_by_task_id(self, task_id: UUID) -> Optional[BroadcastDto]: ...

    async def get_all(self) -> list[BroadcastDto]: ...

    async def update_status(self, task_id: UUID, status: BroadcastStatus) -> None: ...

    async def add_messages(
        self,
        task_id: UUID,
        messages: list[BroadcastMessageDto],
    ) -> list[BroadcastMessageDto]: ...

    async def update_message_status(
        self,
        task_id: UUID,
        telegram_id: int,
        status: BroadcastMessageStatus,
        message_id: Optional[int] = None,
    ) -> None: ...

    async def update_stats(self, task_id: UUID, success_count: int, failed_count: int) -> None: ...

    async def get_active(self) -> list[BroadcastDto]: ...

    async def delete_old(self, days: int = 7) -> int: ...

    async def bulk_update_messages(self, messages: list[BroadcastMessageDto]) -> None: ...
