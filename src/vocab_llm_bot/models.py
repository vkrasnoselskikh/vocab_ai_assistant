import datetime
import uuid

from attr import ib
from pandas.tests.util.test_deprecate_nonkeyword_arguments import i
from sqlalchemy import BigInteger, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger(), unique=True)
    username: Mapped[str | None]
    first_name: Mapped[str | None]
    last_name: Mapped[str | None]
    training_mode: Mapped[str | None]


class UserVocabFile(Base):
    __tablename__ = "user_vocab_files"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    sheet_id: Mapped[str]
    sheet_name: Mapped[str | None] = mapped_column(default=None)
    external_name: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime.datetime | None]


class UserVocabFileLangColumns(Base):
    __tablename__ = "user_vocab_file_columns"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    vocab_file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_vocab_files.id"))
    lang: Mapped[str]
    column_name: Mapped[str]
