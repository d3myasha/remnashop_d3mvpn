from typing import Any, Awaitable, Callable, Optional

from aiogram.types import TelegramObject
from aiogram.types import User as AiogramUser
from dishka import AsyncContainer
from loguru import logger

from src.application.dto.user import UserDTO
from src.application.use_cases.user import UserUseCase
from src.core.constants import CONTAINER_KEY
from src.core.enums import MiddlewareEventType

from .base import EventTypedMiddleware


class UserMiddleware(EventTypedMiddleware):
    __event_types__ = [
        MiddlewareEventType.MESSAGE,
        MiddlewareEventType.CALLBACK_QUERY,
        MiddlewareEventType.ERROR,
        MiddlewareEventType.AIOGD_UPDATE,
        MiddlewareEventType.MY_CHAT_MEMBER,
        MiddlewareEventType.PRE_CHECKOUT_QUERY,
    ]

    async def middleware_logic(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        aiogram_user: Optional[AiogramUser] = self._get_aiogram_user(data)

        if aiogram_user is None or aiogram_user.is_bot:
            logger.warning("Terminating middleware: event from bot or missing user")
            return

        container: AsyncContainer = data[CONTAINER_KEY]
        async with container() as startup_container:
            user_use_case: UserUseCase = await startup_container.get(UserUseCase)

        user = await user_use_case.get_user(aiogram_user.id)
        if user:
            logger.success(user)
        else:
            await user_use_case.register_user(
                UserDTO(
                    telegram_id=aiogram_user.id,
                    username=aiogram_user.username,
                    name=aiogram_user.full_name,
                    language=aiogram_user.language_code,
                )
            )

        return await handler(event, data)
