import datetime
import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column



class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    telegram_id: Mapped[str] = mapped_column(unique=True)
    username: Mapped[str | None]
    first_name: Mapped[str | None]
    last_name: Mapped[str | None]
    training_mode: Mapped[str | None]


class OauthAccessToken(Base):
    __tablename__ = "oauth_access_tokens"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True)
    access_token: Mapped[str] = None
    refresh_token: Mapped[str | None] = None
    expires_in: Mapped[int | None] = None
    expires_at: Mapped[datetime.datetime | None] = None


class UserVocabFile(Base):
    __tablename__ = "user_vocab_files"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    sheet_id: Mapped[str]
    sheet_name: Mapped[str | None] = None
    external_name: Mapped[str | None] = None
    created_at: Mapped[datetime.datetime | None]

class UserVocabFileLangColumns(Base):
    __tablename__ = "user_vocab_file_columns"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    vocab_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_vocab_files.id"))
    lang: Mapped[str]
    column_name: Mapped[str]


class UserWordProgress(Base):
    __tablename__ = "user_word_progress"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    word: Mapped[str]
    is_passed: Mapped[bool] = mapped_column(default=False)
