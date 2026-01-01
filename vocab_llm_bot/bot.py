import uuid
from aiogram import Dispatcher, Bot, Router, F
from aiogram.filters import CommandStart, Command    
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from vocab_llm_bot.models import UserVocabFile
from vocab_llm_bot.google_dict_file import GoogleDictFile

from .config import Config, GoogleServiceAccount
from .database import get_session, get_or_create_user, get_user_vocab_files, create_all_tables

main_router = Router(name=__name__)

bot_email = GoogleServiceAccount().get_client_email()

class GoogleFileForm(StatesGroup):
    enter_link = State()
    enter_sheet_name = State()
    enter_lang_columns = State()


@main_router.message(StateFilter(None), Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    async with get_session() as session:
        # 1. Получаем / создаём пользователя
        user = await get_or_create_user(session, message.from_user)
        user_vocab_files = await get_user_vocab_files(session, user.id)

        if len(user_vocab_files) == 0:
            await message.answer(
                text=("Вы ещё не добавили из Google Sheet ваш словарь .\n"
                "Предоставьте доступ к файлу для почты: " + bot_email + "\n" +
                "А затем Пришлите ссылку на файл:")
            )
            await state.set_state(GoogleFileForm.enter_link)
            
        else:
            file = user_vocab_files[0]
            if not file.sheet_name:
                await message.answer(
                    text="Укажите имя листа со словарём. Пожалуйста, введите его:"
                )
                await state.set_state(GoogleFileForm.enter_sheet_name)
            else:
            # 4. Файлы есть - приветствуем пользователя
                await message.answer("Супер, а у вас уже все настроено. давайте учиться!")

@main_router.message(StateFilter(GoogleFileForm.enter_link), F.text)
async def process_file_link(message: Message, state: FSMContext):
    link = message.text.strip()
    async with get_session() as session:
        # 1. Получаем / создаём пользователя
        user = await get_or_create_user(session, message.from_user)
        # 2. Сохраняем ссылку на файл
        new_vocab_file = UserVocabFile(
            id=uuid.uuid4(),
            user_id=user.id,
            sheet_id=link,
        )
        session.add(new_vocab_file)
        await session.commit()
        await state.set_state(GoogleFileForm.enter_sheet_name)
        await message.answer("Отлично! Теперь укажите имя листа со словарём. Пожалуйста, введите его:")

@main_router.message(StateFilter(GoogleFileForm.enter_sheet_name), F.text)
async def process_sheet_name(message: Message, state: FSMContext):
    sheet_name = message.text.strip()
    async with get_session() as session:
        # 1. Получаем / создаём пользователя
        user = await get_or_create_user(session, message.from_user)
        # 2. Получаем файл
        user_vocab_files = await get_user_vocab_files(session, user.id)
        if not user_vocab_files:
            await message.answer("Ошибка: файл не найден.")
            return
        vocab_file = user_vocab_files[0]
        # 3. Обновляем имя листа
        vocab_file.sheet_name = sheet_name
        session.add(vocab_file)
        await session.commit()
        google_dict_file = GoogleDictFile(google_sheet_id=vocab_file.sheet_id)
        google_dict_file.sheet_name = sheet_name
        header = google_dict_file.get_header()
        # 4. Просим выбрать языковые колонки
        buttons = []
        for idx, col_name in enumerate(header):
            buttons.append(
                InlineKeyboardButton(
                    text=col_name,
                    callback_data=f"select_lang_col:{idx}"
                )
            )
        
        buttons.append(
                InlineKeyboardButton(
                    text="Cохранить настройки",
                    callback_data=f"select_lang_col:{idx}"
                )
            )
        await state.set_state(GoogleFileForm.enter_lang_columns)
        await message.answer(
            "Выберите языковые колонки:",
            reply_markup=InlineKeyboardMarkup(row_width=1, inline_keyboard=[buttons])
        )
       

@main_router.callback_query(StateFilter(GoogleFileForm.enter_lang_columns), F.data.startswith("select_lang_col:"))
async def process_lang_columns(callback_query, state: FSMContext):
    col_index = int(callback_query.data.split(":")[1])
    async with get_session() as session:
        # 1. Получаем / создаём пользователя
        user = await get_or_create_user(session, callback_query.from_user)
        # 2. Получаем файл
        user_vocab_files = await get_user_vocab_files(session, user.id)
        if not user_vocab_files:
            await callback_query.message.answer("Ошибка: файл не найден.")
            return
        vocab_file = user_vocab_files[0]
        # 3. Сохраняем выбранную колонку как язык 1
        # (Для простоты примера сохраняем только одну колонку.
        # В реальном приложении можно реализовать выбор двух колонок)
        from vocab_llm_bot.models import UserVocabFileLangColumns
        lang_column = UserVocabFileLangColumns(
            id=uuid.uuid4(),
            vocab_file_id=vocab_file.id,
            lang="lang_1",  # Здесь можно добавить логику определения языка по имени колонки
            column_index=col_index
        )
        session.add(lang_column)
        await session.commit()

@main_router.callback_query(StateFilter(GoogleFileForm.enter_lang_columns), F.data=="save_settings")
async def save_settings(callback_query, state: FSMContext):
    await callback_query.message.answer("Настройки сохранены! Теперь вы можете начать учить слова.")
    await state.clear()


@main_router.message(StateFilter(None), Command("reset"))
async def reset_settings(message: Message, state: FSMContext):
    await state.clear()

     async with get_session() as session:
        # 1. Получаем / создаём пользователя
        user = await get_or_create_user(session, message.from_user)
        # 2. Получаем файл
        user_vocab_files = await delete_all_user_data(session, user.id)

    await message.answer("Настройки сброшены! Теперь вы можете начать заново.")





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
