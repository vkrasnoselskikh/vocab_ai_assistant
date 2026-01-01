import uuid
from aiogram import Dispatcher, Bot, Router, F
from aiogram.filters import CommandStart, Command    
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
)
from aiogram.fsm.state import StatesGroup, State

from vocab_llm_bot.models import UserVocabFile

from .config import Config, GoogleServiceAccount
from .database import get_session, get_or_create_user, get_user_vocab_files, create_all_tables

main_router = Router(name=__name__)

class Form(StatesGroup):
    google_sheet_link = State()


@main_router.message(Command("start"))
async def cmd_start(message: Message):
    async with get_session() as session:
        # 1. Получаем / создаём пользователя
        user = await get_or_create_user(session, message.from_user)

        # 2. Проверяем наличие Файла у пользователя

        user_vocab_files = await get_user_vocab_files(session, user.id)

        if len(user_vocab_files) == 0:

            bot_email = GoogleServiceAccount().get_client_email()


            await message.answer(
                text=("Вы ещё не добавили из Google Sheet ваш словарь .\n"
                "Предоставьте доступ к файлу для почты: " + bot_email + "\n" +
                "Вставьте ссылку на файл в ответном сообщении."),
                #reply_markup=keyboard,
            )
        else:
            # 4. Файлы есть - приветствуем пользователя
            await message.answer("Супер, а у вас уже все настроено. давайте учиться!")

@main_router.message(F.text)
async def message_with_text(message: Message):
    message_text = message.text.strip()
    # TODO: добавить валидацию ссылки на Google Sheet
    

    async with get_session() as session:
        # 1. Получаем / создаём пользователя
        user = await get_or_create_user(session, message.from_user)

        # 2. Проверяем наличие Файла у пользователя

        user_vocab_files = await get_user_vocab_files(session, user.id)

        if len(user_vocab_files) == 0:
            # 3. Файла нет - сохраняем ссылку
            new_vocab_file = UserVocabFile(
                id=uuid.uuid4(),
                user_id=user.id,
                external_id=message_text,
            )
            session.add(new_vocab_file)
            await session.commit()
            await session.refresh(new_vocab_file)
    await message.answer("Супер, теперь все настроено. давайте учиться!")

async def async_main():
    await create_all_tables()
    bot = Bot(token=Config().telegram_bot_token)
    dp = Dispatcher()
    dp.include_routers(main_router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

def main():
    import asyncio
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
