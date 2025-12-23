from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column

from .base import BaseSQL


class Settings(BaseSQL):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
