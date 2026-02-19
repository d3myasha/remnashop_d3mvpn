from dataclasses import dataclass
from typing import Final, Optional
from uuid import UUID, uuid4

from loguru import logger

from src.application.common import Interactor
from src.application.common.dao import BroadcastDao, PlanDao, SubscriptionDao, UserDao
from src.application.common.policy import Permission
from src.application.common.uow import UnitOfWork
from src.application.dto import BroadcastDto, BroadcastMessageDto, MessagePayloadDto, UserDto
from src.core.enums import BroadcastAudience, BroadcastMessageStatus, BroadcastStatus


@dataclass(frozen=True)
class GetBroadcastAudienceCountDto:
    audience: BroadcastAudience
    plan_id: Optional[int] = None


class GetBroadcastAudienceCount(Interactor[GetBroadcastAudienceCountDto, int]):
    required_permission = Permission.BROADCAST

    def __init__(self, user_dao: UserDao, plan_dao: PlanDao, subscription_dao: SubscriptionDao):
        self.user_dao = user_dao
        self.plan_dao = plan_dao
        self.subscription_dao = subscription_dao

    async def _execute(self, actor: UserDto, data: GetBroadcastAudienceCountDto) -> int:
        audience = data.audience
        plan_id = data.plan_id

        if audience == BroadcastAudience.PLAN:
            if plan_id:
                count = await self.subscription_dao.count_active_by_plan(plan_id)
            else:
                count = await self.plan_dao.count_non_trial()

        elif audience == BroadcastAudience.ALL:
            count = await self.user_dao.count_active_non_blocked()

        elif audience == BroadcastAudience.SUBSCRIBED:
            count = await self.user_dao.count_with_active_subscription()

        elif audience == BroadcastAudience.UNSUBSCRIBED:
            count = await self.user_dao.count_without_subscription()

        elif audience == BroadcastAudience.EXPIRED:
            count = await self.user_dao.count_with_expired_subscription()

        elif audience == BroadcastAudience.TRIAL:
            count = await self.user_dao.count_with_trial_subscription()

        else:
            logger.error(f"{actor.log} Received unknown broadcast audience '{audience}'")
            raise ValueError(f"Unknown broadcast audience '{audience}'")

        logger.info(f"{actor.log} Counted audience '{audience}' (plan_id='{plan_id}'): '{count}'")
        return count


@dataclass(frozen=True)
class GetBroadcastAudienceUsersDto:
    audience: BroadcastAudience
    plan_id: Optional[int] = None


class GetBroadcastAudienceUsers(Interactor[GetBroadcastAudienceUsersDto, list[UserDto]]):
    required_permission = Permission.BROADCAST

    def __init__(self, user_dao: UserDao):
        self._user_dao = user_dao

    async def _execute(self, actor: UserDto, data: GetBroadcastAudienceUsersDto) -> list[UserDto]:
        audience = data.audience
        plan_id = data.plan_id

        if audience == BroadcastAudience.PLAN and plan_id:
            users = await self._user_dao.get_active_by_plan(plan_id)
        elif audience == BroadcastAudience.ALL:
            users = await self._user_dao.get_active_non_blocked()
        elif audience == BroadcastAudience.SUBSCRIBED:
            users = await self._user_dao.get_with_active_subscription()
        elif audience == BroadcastAudience.UNSUBSCRIBED:
            users = await self._user_dao.get_without_subscription()
        elif audience == BroadcastAudience.EXPIRED:
            users = await self._user_dao.get_with_expired_subscription()
        elif audience == BroadcastAudience.TRIAL:
            users = await self._user_dao.get_with_trial_subscription()
        else:
            logger.error(f"{actor.log} Received unknown broadcast audience '{audience}'")
            raise ValueError(f"Unknown broadcast audience '{audience}'")

        logger.info(f"{actor.log} Retrieved '{len(users)}' users for audience '{audience}'")
        return users


@dataclass(frozen=True)
class StartBroadcastDto:
    audience: BroadcastAudience
    payload: MessagePayloadDto
    plan_id: Optional[int] = None


class StartBroadcast(Interactor[StartBroadcastDto, UUID]):
    required_permission = Permission.BROADCAST

    def __init__(
        self,
        uow: UnitOfWork,
        broadcast_dao: BroadcastDao,
        get_broadcast_audience_count: GetBroadcastAudienceCount,
    ):
        self.uow = uow
        self.broadcast_dao = broadcast_dao
        self.get_broadcast_audience_count = get_broadcast_audience_count

    async def _execute(self, actor: UserDto, data: StartBroadcastDto) -> UUID:
        from src.infrastructure.taskiq.tasks.broadcast import send_broadcast_task  # noqa: PLC0415

        total_count = await self.get_broadcast_audience_count.system(
            GetBroadcastAudienceCountDto(data.audience, data.plan_id)
        )

        async with self.uow:
            task_id = uuid4()
            broadcast = BroadcastDto(
                task_id=task_id,
                status=BroadcastStatus.PROCESSING,
                total_count=total_count,
                audience=data.audience,
                payload=data.payload,
            )
            await self.broadcast_dao.create(broadcast)
            await self.uow.commit()

            await (
                send_broadcast_task.kicker()
                .with_task_id(str(task_id))
                .kiq(
                    broadcast,
                    data.plan_id,
                )  # type: ignore[call-overload]
            )

        logger.info(f"{actor.log} Scheduled broadcast initialization '{task_id}'")
        return task_id


@dataclass(frozen=True)
class DeleteBroadcastResultDto:
    total: int
    deleted: int
    failed: int


class DeleteBroadcast(Interactor[UUID, DeleteBroadcastResultDto]):
    required_permission = Permission.BROADCAST

    def __init__(
        self,
        uow: UnitOfWork,
        broadcast_dao: BroadcastDao,
    ):
        self.uow = uow
        self.broadcast_dao = broadcast_dao

    async def _execute(self, actor: UserDto, data: UUID) -> DeleteBroadcastResultDto:
        from src.infrastructure.taskiq.tasks.broadcast import delete_broadcast_task  # noqa: PLC0415

        async with self.uow:
            broadcast = await self.broadcast_dao.get_by_task_id(data)

            if not broadcast:
                logger.error(f"{actor.log} Failed to find broadcast '{data}' for deletion")
                raise ValueError(f"Broadcast '{data}' not found")

            if broadcast.status == BroadcastStatus.DELETED:
                logger.warning(f"{actor.log} Broadcast '{data}' is already deleted")
                raise ValueError("Broadcast already deleted")

            await self.broadcast_dao.update_status(data, BroadcastStatus.DELETED)
            await self.uow.commit()

        logger.info(f"{actor.log} Initiated deletion for broadcast '{data}'")

        task = await delete_broadcast_task.kiq(broadcast)  # type: ignore[call-overload]
        result = await task.wait_result()
        counts = result.return_value

        logger.info(
            f"{actor.log} Finished deletion for '{data}' "
            f"(total: '{counts[0]}', deleted: '{counts[1]}', failed: '{counts[2]}')"
        )
        return DeleteBroadcastResultDto(total=counts[0], deleted=counts[1], failed=counts[2])


class CancelBroadcast(Interactor[UUID, None]):
    required_permission = Permission.BROADCAST

    def __init__(self, uow: UnitOfWork, broadcast_dao: BroadcastDao):
        self.uow = uow
        self.broadcast_dao = broadcast_dao

    async def _execute(self, actor: UserDto, data: UUID) -> None:
        async with self.uow:
            broadcast = await self.broadcast_dao.get_by_task_id(data)

            if not broadcast:
                logger.error(f"{actor.log} Attempted to cancel non-existent broadcast '{data}'")
                raise ValueError(f"Broadcast '{data}' not found")

            if broadcast.status != BroadcastStatus.PROCESSING:
                logger.warning(
                    f"{actor.log} Failed to cancel broadcast '{data}' "
                    f"with status '{broadcast.status}'"
                )
                raise ValueError("Broadcast is not cancelable")

            await self.broadcast_dao.update_status(data, BroadcastStatus.CANCELED)
            await self.uow.commit()

        logger.info(f"{actor.log} Canceled broadcast '{data}'")


@dataclass(frozen=True)
class InitializeBroadcastMessagesDto:
    task_id: UUID
    messages: list[BroadcastMessageDto]


class InitializeBroadcastMessages(
    Interactor[InitializeBroadcastMessagesDto, list[BroadcastMessageDto]],
):
    required_permission = None

    def __init__(self, uow: UnitOfWork, broadcast_dao: BroadcastDao):
        self.uow = uow
        self.broadcast_dao = broadcast_dao

    async def _execute(
        self,
        actor: UserDto,
        data: InitializeBroadcastMessagesDto,
    ) -> list[BroadcastMessageDto]:
        async with self.uow:
            messages = await self.broadcast_dao.add_messages(data.task_id, data.messages)
            await self.uow.commit()

        logger.info(f"Initialized {len(data.messages)} messages for broadcast '{data.task_id}'")
        return messages


@dataclass(frozen=True)
class UpdateBroadcastMessageStatusDto:
    task_id: UUID
    messages: list[BroadcastMessageDto]


class UpdateBroadcastMessageStatus(Interactor[UpdateBroadcastMessageStatusDto, None]):
    required_permission = None

    def __init__(self, uow: UnitOfWork, broadcast_dao: BroadcastDao):
        self.uow = uow
        self.broadcast_dao = broadcast_dao

    async def _execute(self, actor: UserDto, data: UpdateBroadcastMessageStatusDto) -> None:
        success_count = sum(1 for m in data.messages if m.status == BroadcastMessageStatus.SENT)
        failed_count = len(data.messages) - success_count

        async with self.uow:
            await self.broadcast_dao.bulk_update_messages(data.messages)
            await self.broadcast_dao.update_stats(
                data.task_id,
                success_count=success_count,
                failed_count=failed_count,
            )
            await self.uow.commit()


@dataclass(frozen=True)
class FinishBroadcastDto:
    task_id: UUID
    status: BroadcastStatus


class FinishBroadcast(Interactor[FinishBroadcastDto, None]):
    required_permission = None

    def __init__(self, uow: UnitOfWork, broadcast_dao: BroadcastDao):
        self.uow = uow
        self.broadcast_dao = broadcast_dao

    async def _execute(self, actor: UserDto, data: FinishBroadcastDto) -> None:
        async with self.uow:
            await self.broadcast_dao.update_status(data.task_id, data.status)
            await self.uow.commit()

        logger.info(f"Finished broadcast '{data.task_id}' with status '{data.status}'")


class BulkUpdateBroadcastMessages(Interactor[list[BroadcastMessageDto], None]):
    required_permission = None

    def __init__(self, uow: UnitOfWork, broadcast_dao: BroadcastDao):
        self.uow = uow
        self.broadcast_dao = broadcast_dao

    async def _execute(self, actor: UserDto, data: list[BroadcastMessageDto]) -> None:
        async with self.uow:
            await self.broadcast_dao.bulk_update_messages(data)
            await self.uow.commit()

        logger.info(f"Bulk updated {len(data)} messages status")


class ClearOldBroadcasts(Interactor[None, None]):
    required_permission = None

    def __init__(self, uow: UnitOfWork, broadcast_dao: BroadcastDao):
        self.uow = uow
        self.broadcast_dao = broadcast_dao

    async def _execute(self, actor: UserDto, data: None) -> None:
        async with self.uow:
            await self.broadcast_dao.delete_old()
            await self.uow.commit()

        logger.info("Cleaned up old broadcasts from database")


BROADCAST_USE_CASES: Final[tuple[type[Interactor], ...]] = (
    GetBroadcastAudienceCount,
    GetBroadcastAudienceUsers,
    StartBroadcast,
    DeleteBroadcast,
    CancelBroadcast,
    InitializeBroadcastMessages,
    UpdateBroadcastMessageStatus,
    FinishBroadcast,
    BulkUpdateBroadcastMessages,
    ClearOldBroadcasts,
)
