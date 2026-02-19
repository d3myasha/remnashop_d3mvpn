from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram_dialog import DialogManager
from aiogram_dialog.api.exceptions import UnknownIntent, UnknownState
from aiogram_dialog.widgets.kbd import Button
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject
from loguru import logger

from src.application.common import TranslatorRunner
from src.application.common.policy import Permission, PermissionPolicy
from src.application.dto import UserDto
from src.core.config import AppConfig
from src.core.exceptions import PermissionDeniedError
from src.infrastructure.taskiq.tasks.update import check_bot_update

router = Router(name=__name__)


@inject
@router.message(Command("test"))
async def on_test_command(
    message: Message,
    user: UserDto,
    config: AppConfig,
    # start_broadcast: FromDishka[StartBroadcast],
) -> None:
    if not PermissionPolicy.has_permission(user, Permission.COMMAND_TEST):
        raise PermissionDeniedError

    logger.info(f"{user.log} Test command executed")

    # await start_broadcast(
    #     user,
    #     StartBroadcastDto(
    #         BroadcastAudience.ALL,
    #         MessagePayloadDto(
    #             i18n_key="ntf-broadcast.message",
    #             i18n_kwargs={"content": "рассылка <b>проверка</b>"},
    #             delete_after=None,
    #         ),
    #     ),
    # )
    # raise UnknownState


@inject
async def show_dev_popup(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    i18n: FromDishka[TranslatorRunner],
) -> None:
    await callback.answer(text=i18n.get("development"), show_alert=True)
