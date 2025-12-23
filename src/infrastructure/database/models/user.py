from typing import Optional

from sqlalchemy import BigInteger, Boolean, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.enums import Locale, UserRole

from .base import BaseSQL
from .timestamp import TimestampMixin


class User(BaseSQL, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    username: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    referral_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            native_enum=True,
        ),
        default=UserRole.USER,
        nullable=False,
    )
    language: Mapped[Locale] = mapped_column(
        Enum(
            Locale,
            name="locale",
            native_enum=True,
        ),
        default=Locale.RU,
        nullable=False,
    )

    personal_discount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    purchase_discount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_bot_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_rules_accepted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
