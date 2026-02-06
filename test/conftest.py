import asyncio
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from vocab_llm_bot.models import Base, User


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def engine():
    return create_async_engine("sqlite+aiosqlite:///:memory:")


@pytest.fixture(scope="session")
async def tables(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def dbsession(engine, tables):
    """Returns an sqlalchemy session, and after the test tears down everything properly."""
    connection = await engine.connect()
    # begin the nested transaction
    trans = await connection.begin()
    Session = sessionmaker(connection, expire_on_commit=False, class_=AsyncSession)
    session = Session()

    yield session

    # roll back the broader transaction
    await trans.rollback()
    # put back the connection to the connection pool
    await connection.close()
    await session.close()  # type: ignore


@pytest.fixture
async def orm_user(dbsession: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        telegram_id="12345",
        username="testuser",
        first_name="Test",
        last_name="User",
    )
    dbsession.add(user)
    await dbsession.commit()
    return user
