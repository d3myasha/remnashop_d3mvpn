import uuid
from dataclasses import dataclass
from typing import Any, Final, Optional
from uuid import UUID

from loguru import logger
from pydantic import SecretStr

from src.application.common import Interactor, Notifier, TranslatorHub
from src.application.common.dao import PaymentGatewayDao, TransactionDao
from src.application.common.policy import Permission
from src.application.common.uow import UnitOfWork
from src.application.dto import (
    PaymentResultDto,
    PlanSnapshotDto,
    PriceDetailsDto,
    TransactionDto,
    UserDto,
)
from src.application.dto.payment_gateway import (
    AnyGatewaySettingsDto,
    CryptomusGatewaySettingsDto,
    CryptopayGatewaySettingsDto,
    HeleketGatewaySettingsDto,
    PaymentGatewayDto,
    RobokassaGatewaySettingsDto,
    YookassaGatewaySettingsDto,
    YoomoneyGatewaySettingsDto,
)
from src.core.enums import Currency, PaymentGatewayType, PurchaseType, TransactionStatus
from src.core.exceptions import GatewayNotConfiguredError
from src.core.utils.i18n_helpers import i18n_format_days
from src.infrastructure.payment_gateways import PaymentGatewayFactory
from src.infrastructure.payment_gateways.base import BasePaymentGateway


class GetPaymentGatewayInstance(Interactor[PaymentGatewayType, BasePaymentGateway]):
    required_permission = None

    def __init__(
        self,
        uow: UnitOfWork,
        payment_gateway_dao: PaymentGatewayDao,
        gateway_factory: PaymentGatewayFactory,
    ) -> None:
        self.uow = uow
        self.payment_gateway_dao = payment_gateway_dao
        self.gateway_factory = gateway_factory

    async def _execute(
        self,
        actor: UserDto,
        gateway_type: PaymentGatewayType,
    ) -> BasePaymentGateway:
        gateway = await self.payment_gateway_dao.get_by_type(gateway_type)

        if not gateway:
            raise ValueError(f"Payment gateway of type '{gateway_type}' not found")

        return self.gateway_factory(gateway)


class MovePaymentGatewayUp(Interactor[int, None]):
    required_permission = Permission.REMNASHOP_GATEWAYS

    def __init__(self, uow: UnitOfWork, gateway_dao: PaymentGatewayDao) -> None:
        self.uow = uow
        self.gateway_dao = gateway_dao

    async def _execute(self, actor: UserDto, gateway_id: int) -> None:
        async with self.uow:
            gateways = await self.gateway_dao.get_all()
            gateways.sort(key=lambda g: g.order_index)

            index = next((i for i, g in enumerate(gateways) if g.id == gateway_id), None)

            if index is None:
                logger.warning(
                    f"Payment gateway with id '{gateway_id}' not found for move operation"
                )
                return

            if index == 0:
                gateway = gateways.pop(0)
                gateways.append(gateway)
                logger.debug(f"Payment gateway '{gateway_id}' moved from top to bottom")
            else:
                gateways[index - 1], gateways[index] = gateways[index], gateways[index - 1]
                logger.debug(f"Payment gateway '{gateway_id}' moved up one position")

            for i, g in enumerate(gateways, start=1):
                if g.order_index != i:
                    g.order_index = i
                    await self.gateway_dao.update(g)

            await self.uow.commit()

        logger.info(f"{actor.log} Moved payment gateway '{gateway_id}' up successfully")


class TogglePaymentGatewayActive(Interactor[int, None]):
    required_permission = Permission.REMNASHOP_GATEWAYS

    def __init__(
        self,
        uow: UnitOfWork,
        gateway_dao: PaymentGatewayDao,
    ) -> None:
        self.uow = uow
        self.gateway_dao = gateway_dao

    async def _execute(self, actor: UserDto, gateway_id: int) -> None:
        async with self.uow:
            gateway = await self.gateway_dao.get_by_id(gateway_id)

            if not gateway:
                raise ValueError(f"Payment gateway with id '{gateway_id}' not found")

            if gateway.settings and not gateway.settings.is_configured:
                raise GatewayNotConfiguredError(f"Gateway '{gateway_id}' is not configured")

            old_status = gateway.is_active
            gateway.is_active = not old_status

            await self.gateway_dao.update(gateway)
            await self.uow.commit()

        logger.info(
            f"{actor.log} Updated payment gateway '{gateway_id}' "
            f"active status from '{old_status}' to '{gateway.is_active}'"
        )


@dataclass(frozen=True)
class UpdatePaymentGatewaySettingsDto:
    gateway_id: int
    field_name: str
    value: str


class UpdatePaymentGatewaySettings(Interactor[UpdatePaymentGatewaySettingsDto, None]):
    required_permission = Permission.REMNASHOP_GATEWAYS

    def __init__(self, uow: UnitOfWork, gateway_dao: PaymentGatewayDao) -> None:
        self.uow = uow
        self.gateway_dao = gateway_dao

    async def _execute(self, actor: UserDto, data: UpdatePaymentGatewaySettingsDto) -> None:
        async with self.uow:
            gateway = await self.gateway_dao.get_by_id(data.gateway_id)

            if not gateway or not gateway.settings:
                raise GatewayNotConfiguredError(f"Gateway '{data.gateway_id}' is not configured")
            try:
                new_value: Any = data.value
                if data.field_name in ["api_key", "secret_key"] and isinstance(new_value, str):
                    new_value = SecretStr(new_value)

                setattr(gateway.settings, data.field_name, new_value)

                await self.gateway_dao.update(gateway)
                await self.uow.commit()

                logger.info(
                    f"{actor.log} Updated '{data.field_name}' for gateway '{data.gateway_id}'"
                )

            except ValueError as e:
                logger.warning(f"{actor.log} Invalid value for field '{data.field_name}': {e}")
                raise


class CreateDefaultPaymentGateway(Interactor[None, None]):
    required_permission = None

    def __init__(self, uow: UnitOfWork, gateway_dao: PaymentGatewayDao) -> None:
        self.uow = uow
        self.gateway_dao = gateway_dao

    async def _execute(self, actor: UserDto, data: None) -> None:
        async with self.uow:
            for gateway_type in PaymentGatewayType:
                if await self.gateway_dao.get_by_type(gateway_type):
                    continue

                is_active = gateway_type == PaymentGatewayType.TELEGRAM_STARS

                settings_map = {
                    PaymentGatewayType.YOOKASSA: YookassaGatewaySettingsDto,
                    PaymentGatewayType.YOOMONEY: YoomoneyGatewaySettingsDto,
                    PaymentGatewayType.CRYPTOMUS: CryptomusGatewaySettingsDto,
                    PaymentGatewayType.HELEKET: HeleketGatewaySettingsDto,
                    PaymentGatewayType.CRYPTOPAY: CryptopayGatewaySettingsDto,
                    PaymentGatewayType.ROBOKASSA: RobokassaGatewaySettingsDto,
                }
                dto_class = settings_map.get(gateway_type)
                settings = dto_class() if dto_class else None

                await self.gateway_dao.create(
                    PaymentGatewayDto(
                        type=gateway_type,
                        currency=Currency.from_gateway_type(gateway_type),
                        is_active=is_active,
                        settings=settings,
                    )
                )
                logger.info(f"Payment gateway '{gateway_type}' created")

            await self.uow.commit()


@dataclass(frozen=True)
class CreatePaymentDto:
    plan_snapshot: PlanSnapshotDto
    pricing: PriceDetailsDto
    purchase_type: PurchaseType
    gateway_type: PaymentGatewayType


class CreatePayment(Interactor[CreatePaymentDto, PaymentResultDto]):
    required_permission = None

    def __init__(
        self,
        uow: UnitOfWork,
        payment_gateway_dao: PaymentGatewayDao,
        transaction_dao: TransactionDao,
        gateway_factory: PaymentGatewayFactory,
        translator_hub: TranslatorHub,
    ) -> None:
        self.uow = uow
        self.payment_gateway_dao = payment_gateway_dao
        self.transaction_dao = transaction_dao
        self.gateway_factory = gateway_factory
        self.translator_hub = translator_hub

    async def _execute(self, actor: UserDto, data: CreatePaymentDto) -> PaymentResultDto:
        gateway = await self.payment_gateway_dao.get_by_type(data.gateway_type)

        if not gateway:
            raise ValueError(f"Payment gateway of type '{data.gateway_type}' not found")

        gateway_instance = self.gateway_factory(gateway)
        i18n = self.translator_hub.get_translator_by_locale(actor.language)

        key, kw = i18n_format_days(data.plan_snapshot.duration)
        details = i18n.get(
            "payment-invoice-description",
            purchase_type=data.purchase_type,
            name=data.plan_snapshot.name,
            duration=i18n.get(key, **kw),
        )

        transaction = TransactionDto(
            payment_id=uuid.uuid4(),
            status=TransactionStatus.PENDING,
            purchase_type=data.purchase_type,
            gateway_type=gateway_instance.data.type,
            pricing=data.pricing,
            currency=gateway_instance.data.currency,
            plan_snapshot=data.plan_snapshot,
        )

        async with self.uow:
            if data.pricing.is_free:
                await self.transaction_dao.create(transaction)
                await self.uow.commit()

                logger.info(
                    f"Payment for user '{actor.telegram_id}' not created because pricing is free"
                )
                return PaymentResultDto(id=transaction.payment_id, url=None)

            payment: PaymentResultDto = await gateway_instance.handle_create_payment(
                amount=data.pricing.final_amount,
                details=details,
            )

            transaction.payment_id = payment.id
            await self.transaction_dao.create(transaction)
            await self.uow.commit()

        logger.info(f"Created transaction '{payment.id}' for user '{actor.telegram_id}'")
        return payment


class CreateTestPayment(Interactor[PaymentGatewayType, PaymentResultDto]):
    required_permission = None

    def __init__(
        self,
        uow: UnitOfWork,
        payment_gateway_dao: PaymentGatewayDao,
        transaction_dao: TransactionDao,
        gateway_factory: PaymentGatewayFactory,
        translator_hub: TranslatorHub,
    ) -> None:
        self.uow = uow
        self.payment_gateway_dao = payment_gateway_dao
        self.transaction_dao = transaction_dao
        self.gateway_factory = gateway_factory
        self.translator_hub = translator_hub

    async def _execute(self, actor: UserDto, gateway_type: PaymentGatewayType) -> PaymentResultDto:
        gateway = await self.payment_gateway_dao.get_by_type(gateway_type)

        if not gateway:
            raise ValueError(f"Payment gateway of type '{gateway_type}' not found")

        gateway_instance = self.gateway_factory(gateway)
        i18n = self.translator_hub.get_translator_by_locale(actor.language)

        test_pricing = PriceDetailsDto.test()
        test_plan_snapshot = PlanSnapshotDto.test()

        payment: PaymentResultDto = await gateway_instance.handle_create_payment(
            amount=test_pricing.final_amount,
            details=i18n.get("test-payment"),
        )

        async with self.uow:
            transaction = TransactionDto(
                payment_id=payment.id,
                status=TransactionStatus.PENDING,
                is_test=True,
                purchase_type=PurchaseType.NEW,
                gateway_type=gateway_instance.data.type,
                pricing=test_pricing,
                currency=gateway_instance.data.currency,
                plan_snapshot=test_plan_snapshot,
            )
            await self.transaction_dao.create(transaction)
            await self.uow.commit()

        logger.info(f"Created test transaction '{payment.id}' for user '{actor.telegram_id}'")
        return payment


# class ProcessPaymentWebhook(Interactor[tuple[UUID, TransactionStatus], None]):
#     def __init__(
#         self,
#         uow: UnitOfWork,
#         transaction_dao: TransactionDao,
#         subscription_dao: SubscriptionDao,
#         notifier: Notifier,
#         referral_dao: ReferralDao,
#     ) -> None:
#         self.uow = uow
#         self.transaction_dao = transaction_dao
#         self.subscription_dao = subscription_dao
#         self.referral_dao = referral_dao
#         self.notifier = notifier

#     async def _execute(self, actor: UserDto, data: tuple[UUID, TransactionStatus]) -> None:
#         payment_id, new_status = data

#         async with self.uow:
#             transaction = await self.transaction_dao.get(payment_id)

#             if not transaction or not transaction.user:
#                 logger.critical(f"Transaction or user not found for '{payment_id}'")
#                 return

#             if transaction.is_completed:
#                 logger.warning(f"Transaction '{payment_id}' for user '{transaction.user.telegram_id}' already completed")
#                 return

#             if new_status == TransactionStatus.CANCELED:
#                 transaction.status = TransactionStatus.CANCELED
#                 await self.transaction_dao.update(transaction)
#                 await self.uow.commit()
#                 logger.info(f"Payment canceled '{payment_id}' for user '{transaction.user.telegram_id}'")
#                 return

#             if new_status == TransactionStatus.COMPLETED:
#                 transaction.status = TransactionStatus.COMPLETED
#                 await self.transaction_dao.update(transaction)

#                 await self._handle_success(transaction)
#                 await self.uow.commit()
#                 logger.info(f"Payment succeeded '{payment_id}' for user '{transaction.user.telegram_id}'")

#     async self._handle_success(self, transaction: TransactionDto) -> None:
#         if transaction.is_test:
#             await self.notification_service.notify_user(
#                 user=transaction.user,
#                 i18n_key="ntf-gateway-test-payment-confirmed"
#             )
#             return

#         subscription = await self.subscription_service.get_current(transaction.user.telegram_id)


#         await self.notification_service.system_notify(
#             ntf_type=SystemNotificationType.SUBSCRIPTION,
#             payload=MessagePayload.not_deleted(
#                 i18n_key=self._get_i18n_key(transaction.purchase_type),
#                 i18n_kwargs={**i18n_kwargs, **extra_i18n_kwargs},
#                 reply_markup=get_user_keyboard(transaction.user.telegram_id),
#             ),
#         )

#         await purchase_subscription_task.kiq(transaction, subscription)

#         if not transaction.pricing.is_free:
#             await self.referral_service.assign_referral_rewards(transaction=transaction)

#     def _get_i18n_key(self, p_type: PurchaseType) -> str:
#         return {
#             PurchaseType.NEW: "ntf-event-subscription-new",
#             PurchaseType.RENEW: "ntf-event-subscription-renew",
#             PurchaseType.CHANGE: "ntf-event-subscription-change",
#         }[p_type]

GATEWAYS_USE_CASES: Final[tuple[type[Interactor], ...]] = (
    GetPaymentGatewayInstance,
    MovePaymentGatewayUp,
    TogglePaymentGatewayActive,
    UpdatePaymentGatewaySettings,
    CreateDefaultPaymentGateway,
    CreatePayment,
    CreateTestPayment,
)
