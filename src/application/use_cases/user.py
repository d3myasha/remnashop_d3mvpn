from typing import Optional

from loguru import logger

from src.application.dto import UserDTO
from src.application.protocols import UserDAO
from src.core.config import AppConfig
from src.core.enums import UserRole
from src.core.utils.generators import generate_referral_code
from src.infrastructure.database.uow import UnitOfWork


class UserUseCase:
    def __init__(self, dao: UserDAO, uow: UnitOfWork, config: AppConfig) -> None:
        self.dao = dao
        self.uow = uow
        self.config = config

    async def register_user(self, user_dto: UserDTO) -> UserDTO:
        # Use Case управляет транзакцией через UOW
        async with self.uow:
            # DAO просто делает свою работу с данными
            user_dto.referral_code = generate_referral_code(
                user_dto.telegram_id,
                secret=self.config.crypt_key.get_secret_value(),
            )
            user_dto.role = (
                UserRole.DEV if self.config.bot.dev_id == user_dto.telegram_id else UserRole.USER
            )

            user_dto.language = (
                user_dto.language
                if user_dto.language in self.config.locales
                else self.config.default_locale
            )

            new_user = await self.dao.create(user_dto)

            # Если здесь что-то упадет, UOW сам сделает rollback
            # так как мы находимся внутри контекстного менеджера

            await self.uow.commit()
            logger.info(f"User '{user_dto.telegram_id}' registration committed via UOW")

            return new_user

    async def get_user(self, telegram_id: int) -> Optional[UserDTO]:
        async with self.uow:
            return await self.dao.get(telegram_id)
