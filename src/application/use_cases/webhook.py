from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.methods import SetWebhook
from aiogram.types import WebhookInfo
from loguru import logger

from src.application.protocols import WebhookDAO
from src.core.config import AppConfig
from src.core.security.crypto import get_webhook_hash
from src.core.utils.time import datetime_now


class WebhookUseCase:
    def __init__(self, dao: WebhookDAO, bot: Bot, config: AppConfig) -> None:
        self.dao = dao
        self.bot = bot
        self.config = config

    async def setup(self, allowed_updates: list[str]) -> WebhookInfo:
        safe_url = self.config.bot.safe_webhook_url(domain=self.config.domain)

        webhook_request = SetWebhook(
            url=self.config.bot.webhook_url(domain=self.config.domain).get_secret_value(),
            allowed_updates=allowed_updates,
            drop_pending_updates=self.config.bot.drop_pending_updates,
            secret_token=self.config.bot.secret_token.get_secret_value(),
        )

        webhook_hash = get_webhook_hash(webhook_request.model_dump(exclude_unset=True))

        if await self.dao.is_hash_exists(self.bot.id, webhook_hash):
            if not self.config.bot.reset_webhook:
                logger.info(f"Webhook setup skipped for bot '{self.bot.id}', hash matches")
                return await self.bot.get_webhook_info()

        if not await self.bot(webhook_request):
            logger.error(f"Failed to set webhook for bot '{self.bot.id}' on URL '{safe_url}'")
            raise RuntimeError(f"Could not set webhook for bot '{self.bot.id}'")

        await self.dao.clear_all_hashes(self.bot.id)
        await self.dao.save_hash(self.bot.id, webhook_hash)

        logger.info(f"Webhook set successfully for bot '{self.bot.id}' to URL '{safe_url}'")
        return await self.bot.get_webhook_info()

    async def delete(self) -> None:
        if not self.config.bot.reset_webhook:
            logger.debug(f"Webhook reset disabled in config for bot '{self.bot.id}'")
            return

        if await self.bot.delete_webhook():
            await self.dao.clear_all_hashes(self.bot.id)
            logger.info(f"Webhook deleted successfully for bot '{self.bot.id}'")
        else:
            logger.error(f"Failed to delete webhook for bot '{self.bot.id}'")

    def has_error(self, webhook_info: WebhookInfo) -> bool:
        if not webhook_info.last_error_message or webhook_info.last_error_date is None:
            return False

        is_new = self._is_new_error(error_time=webhook_info.last_error_date)
        if is_new:
            logger.warning(f"Recent webhook error detected for bot '{self.bot.id}'")

        return is_new

    def _is_new_error(self, error_time: datetime, tolerance: int = 1) -> bool:
        current_time = datetime_now()
        time_difference = current_time - error_time
        return time_difference <= timedelta(seconds=tolerance)
