import asyncio
import datetime
import uuid

from google.oauth2.credentials import Credentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from vocab_llm_bot.config import DATABASE_URL
from vocab_llm_bot.models import User, OauthAccessToken, Base

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


async def save_access_token_for_user(session: AsyncSession, user_id, credentials: Credentials) -> OauthAccessToken:
    if isinstance(user_id, str):
        user_id = uuid.UUID(user_id)
    stmt = select(OauthAccessToken).where(OauthAccessToken.user_id == user_id)
    res = (await session.execute(stmt)).scalar_one_or_none()

    if res is None:
        print(credentials.expiry)
        token = OauthAccessToken(
            id=uuid.uuid4(),
            user_id=user_id,
            access_token=credentials.token,
            refresh_token=credentials.refresh_token,
            expires_at=credentials.expiry,
        )
        session.add(token)
        await session.commit()
        return token
    else:
        res: OauthAccessToken
        res.access_token = credentials.token
        if credentials.refresh_token:
            res.refresh_token = credentials.refresh_token
        res.expires_at = credentials.expiry
        session.add(res)
        await session.commit()
        return res


async def get_access_token_for_user(session: AsyncSession, user_id) -> OauthAccessToken | None:
    if isinstance(user_id, str):
        user_id = uuid.UUID(user_id)
    access_token_stmt = select(OauthAccessToken).where(OauthAccessToken.user_id == user_id)
    return (await session.execute(access_token_stmt)).scalar_one_or_none()


if __name__ == '__main__':
    asyncio.run(create_all_tables())