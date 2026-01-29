import asyncio
import datetime
import uuid

from google.oauth2.credentials import Credentials
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from vocab_llm_bot.config import DATABASE_URL
from vocab_llm_bot.models import Base, User, UserVocabFile, UserVocabFileLangColumns

async_engine = create_async_engine(f"sqlite+aiosqlite:///{str(DATABASE_URL)}")
get_session = async_sessionmaker(
    bind=async_engine,
    expire_on_commit=False,
)


async def create_all_tables():
    async with async_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def get_or_create_user(session: AsyncSession, tg_user) -> User:
    """
    Создаём пользователя в БД, если его ещё нет.
    Предполагаем, что в модели User есть поле telegram_id.
    """
    stmt = select(User).where(User.telegram_id == tg_user.id)
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user is None:
        user = User(
            id=uuid.uuid4(),
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def create_uesr_vocab_file(
    session: AsyncSession, user_id: uuid.UUID, google_file_id: str
):
    new_vocab_file = UserVocabFile(
        id=uuid.uuid4(),
        user_id=user_id,
        sheet_id=google_file_id,
    )
    session.add(new_vocab_file)
    await session.commit()


async def get_user_vocab_files(session: AsyncSession, user_id) -> list[UserVocabFile]:
    stmt = select(UserVocabFile).where(UserVocabFile.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalars().all()


async def get_user_vocab_file_lang_columns(
    session: AsyncSession, vocab_file_id
) -> list[UserVocabFileLangColumns]:
    stmt = select(UserVocabFileLangColumns).where(
        UserVocabFileLangColumns.vocab_file_id == vocab_file_id
    )
    result = await session.execute(stmt)
    return result.scalars().all()



async def delete_all_user_data(user_id: uuid.UUID):
    async with get_session() as session:
        await session.execute(
            delete(UserVocabFileLangColumns).where(
                UserVocabFileLangColumns.vocab_file_id.in_(
                    select(UserVocabFile.id).where(UserVocabFile.user_id == user_id)
                )
            )
        )
        # Удаляем связанные записи в других таблицах, если необходимо
        await session.execute(
            delete(UserVocabFile).where(UserVocabFile.user_id == user_id)
        )

        await session.commit()


if __name__ == "__main__":
    asyncio.run(create_all_tables())
