from contextlib import asynccontextmanager
from typing import AsyncGenerator

from aiogram import Dispatcher
from aiogram.types import WebhookInfo
from dishka import AsyncContainer, Scope
from fastapi import FastAPI
from loguru import logger

from src.api.endpoints import TelegramWebhookEndpoint
from src.application.use_cases.command import CommandUseCase
from src.application.use_cases.webhook import WebhookUseCase


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    dispatcher: Dispatcher = app.state.dispatcher
    telegram_webhook_endpoint: TelegramWebhookEndpoint = app.state.telegram_webhook_endpoint
    container: AsyncContainer = app.state.dishka_container

    async with container(scope=Scope.REQUEST) as startup_container:
        webhook: WebhookUseCase = await startup_container.get(WebhookUseCase)
        command: CommandUseCase = await startup_container.get(CommandUseCase)

    await startup_container.close()

    allowed_updates = dispatcher.resolve_used_update_types()
    webhook_info: WebhookInfo = await webhook.setup(allowed_updates)

    if webhook.has_error(webhook_info):
        logger.critical(f"Webhook has a last error message: '{webhook_info.last_error_message}'")

    await command.setup()
    await telegram_webhook_endpoint.startup()

    yield

    await telegram_webhook_endpoint.shutdown()
    await command.delete()
    await webhook.delete()
    await container.close()
