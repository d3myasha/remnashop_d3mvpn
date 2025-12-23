from dishka import Provider, Scope, provide

from src.application.protocols import UserDAO, WebhookDAO
from src.infrastructure.database.dao import UserDAOImpl, WebhookDAOImpl


class DaoProvider(Provider):
    scope = Scope.APP

    webhook = provide(source=WebhookDAOImpl, provides=WebhookDAO)
    user = provide(source=UserDAOImpl, provides=UserDAO, scope=Scope.REQUEST)
