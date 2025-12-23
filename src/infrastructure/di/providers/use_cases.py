from dishka import Provider, Scope, provide

from src.application.use_cases.command import CommandUseCase
from src.application.use_cases.user import UserUseCase
from src.application.use_cases.webhook import WebhookUseCase


class UseCasesProvider(Provider):
    scope = Scope.APP

    command = provide(source=CommandUseCase)
    webhook = provide(source=WebhookUseCase)
    user = provide(UserUseCase, scope=Scope.REQUEST)
