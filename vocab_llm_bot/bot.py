from aiogram import Dispatcher, Bot
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message, WebAppInfo,
)

from config import Config, GoogleAuthConfig
from database import get_session, get_or_create_user, get_access_token_for_user
from vocab_llm_bot.server import app


async def cmd_start(message: Message):
    async with get_session() as session:
        # 1. Получаем / создаём пользователя
        user = await get_or_create_user(session, message.from_user)

        # 2. Проверяем наличие OauthAccessToken

        access_token = await get_access_token_for_user(session, user.id)

        if access_token is None:
            auth_url = GoogleAuthConfig().authorize_url + f"?state={user.id}"

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Sign in Google",
                            web_app=WebAppInfo(url=auth_url),
                        )
                    ]
                ]
            )

            await message.answer(
                "Вы ещё не добавили из Google Sheet ваш словарь .\n"
                "Нажмите кнопку ниже, чтобы пройти авторизацию:",
                reply_markup=keyboard,
            )
        else:
            # 4. Токен есть — показываем список файлов
            await message.answer("У вас пока нет добавленных файлов.")

async def main():
    bot = Bot(token=Config().telegram_bot_token)
    dp = Dispatcher()
    app['bot'] = bot

    # Регистрируем хэндлер для /start
    dp.message.register(cmd_start, CommandStart())
    #web.run_app(app, port=8000, host='0.0.0.0')
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())