import asyncio
import datetime
import uuid

from google.oauth2.credentials import Credentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from vocab_llm_bot.config import DATABASE_URL
from vocab_llm_bot.models import User, Base, UserVocabFile

async_engine = create_async_engine(f"sqlite+aiosqlite:///{str(DATABASE_URL)}")
get_session = async_sessionmaker(bind=async_engine, expire_on_commit=False, )


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

async def get_user_vocab_files(session: AsyncSession, user_id) -> list[UserVocabFile]:
    stmt = select(UserVocabFile).where(UserVocabFile.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalars().all()


if __name__ == '__main__':
    asyncio.run(create_all_tables())