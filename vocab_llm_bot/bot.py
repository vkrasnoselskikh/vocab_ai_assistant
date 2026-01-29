from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.types import Message, TelegramObject
from sqlalchemy.ext.asyncio.session import AsyncSession

from .config import Config
from .database import create_all_tables, get_or_create_user, get_session
from .handlers import learning, setup


# ========== MIDDLEWARES ==========
class DbSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        async with get_session() as session:
            data["orm_user"] = await get_or_create_user(session, event.from_user)
            data["session"] = session
            return await handler(event, data)


# ========== MAIN ==========
async def async_main():
    await create_all_tables()
    bot = Bot(token=Config().telegram_bot_token)
    dp = Dispatcher()

    dp.message.middleware(DbSessionMiddleware())

    dp.include_routers(setup.setup_router, learning.learning_router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


def main():
    import asyncio

    asyncio.run(async_main())


if __name__ == "__main__":
    main()
