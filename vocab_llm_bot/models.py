import datetime
import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    telegram_id: Mapped[str] = mapped_column(unique=True)
    username: Mapped[str | None]
    first_name: Mapped[str | None]
    last_name: Mapped[str | None]


class OauthAccessToken(Base):
    __tablename__ = "oauth_access_tokens"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True)
    access_token: Mapped[str] = None
    refresh_token: Mapped[str | None] = None
    expires_in: Mapped[int | None] = None
    expires_at: Mapped[datetime.datetime | None] = None


class UserVocabFiles(Base):
    __tablename__ = "user_vocab_files"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    external_id: Mapped[str]
    external_name: Mapped[str | None]
    created_at: Mapped[datetime.datetime | None]
