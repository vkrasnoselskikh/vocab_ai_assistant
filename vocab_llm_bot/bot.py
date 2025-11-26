import uuid
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    TelegramObject,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio.session import AsyncSession

from .config import Config, GoogleServiceAccount
from .database import (
    create_all_tables,
    create_uesr_vocab_file,
    delete_all_user_data,
    get_or_create_user,
    get_session,
    get_user_vocab_files,
)
from .google_dict_file import GoogleDictFile
from .models import User, UserVocabFileLangColumns
from .training_strategies import WorldPairTrainStrategy

setup_router = Router(name="setup")
learning_router = Router(name="learning")

bot_email = GoogleServiceAccount().get_client_email()


# FSM только для настройки
class GoogleFileForm(StatesGroup):
    enter_link = State()
    enter_sheet_name = State()
    enter_lang_columns = State()


# ========== SETUP ROUTER ==========
#
class SetupRouterContext(BaseMiddleware):
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


setup_router.message.middleware(SetupRouterContext())


@setup_router.message(StateFilter(None), Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    async with get_session() as session:
        user = await get_or_create_user(session, message.from_user)
        user_vocab_files = await get_user_vocab_files(session, user.id)

        if len(user_vocab_files) == 0:
            await message.answer(
                text=(
                    "Вы ещё не добавили из Google Sheet ваш словарь .\n"
                    "Предоставьте доступ к файлу для почты: "
                    + bot_email
                    + "\n"
                    + "А затем Пришлите ссылку на файл:"
                )
            )
            await state.set_state(GoogleFileForm.enter_link)
        else:
            await message.answer(
                text="У вас уже все настроено. Начните учить слова командой /learn"
            )


@setup_router.message(StateFilter(GoogleFileForm.enter_link), F.text)
async def process_file_link(
    message: Message, state: FSMContext, session: AsyncSession, orm_user: User
):
    link = message.text.strip()
    await create_uesr_vocab_file(session, user_id=orm_user.id, google_file_id=link)
    await state.set_state(GoogleFileForm.enter_sheet_name)
    await message.answer(
        "Отлично! Теперь укажите имя листа со словарём. Пожалуйста, введите его:"
    )


def get_column_selection_keyboard(header_list: list[str], selected_indices: list[int]):
    builder = InlineKeyboardBuilder()
    for idx, col_name in enumerate(header_list):
        checkbox = "✅ " if idx in selected_indices else ""
        builder.row(
            InlineKeyboardButton(
                text=f"{checkbox}{col_name}", callback_data=f"select_lang_col:{idx}"
            )
        )

    builder.row(
        InlineKeyboardButton(
            text="💾 Сохранить настройки", callback_data="save_settings"
        )
    )
    return builder.as_markup()


@setup_router.message(StateFilter(GoogleFileForm.enter_sheet_name), F.text)
async def process_sheet_name(
    message: Message, state: FSMContext, session: AsyncSession, orm_user: User
):
    sheet_name = message.text.strip()
    user_vocab_files = await get_user_vocab_files(session, orm_user.id)
    if not user_vocab_files:
        await message.answer("Ошибка: файл не найден.")
        return

    vocab_file = user_vocab_files[0]
    vocab_file.sheet_name = sheet_name
    session.add(vocab_file)
    await session.commit()

    google_dict_file = GoogleDictFile(google_sheet_id=vocab_file.sheet_id)
    google_dict_file.sheet_name = sheet_name
    header = google_dict_file.get_header()

    # Инициализируем данные в состоянии для отслеживания выбора пользователя
    await state.update_data(header=header, selected_indices=[])

    # Формируем список кнопок через функцию
    await state.set_state(GoogleFileForm.enter_lang_columns)
    await message.answer(
        "Выберите языковые колонки:",
        reply_markup=get_column_selection_keyboard(header, []),
    )


@setup_router.callback_query(
    StateFilter(GoogleFileForm.enter_lang_columns),
    F.data.startswith("select_lang_col:"),
)
async def process_lang_columns(callback_query, state: FSMContext):
    # Достаем ID колонки из callback_data
    col_index = int(callback_query.data.split(":")[1])

    # Получаем текущие данные из FSM
    data = await state.get_data()
    header = data.get("header", [])
    selected_indices = data.get("selected_indices", [])

    # Переключаем состояние (toggle)
    if col_index in selected_indices:
        selected_indices.remove(col_index)
    else:
        selected_indices.add(col_index) if isinstance(selected_indices, set) else None
        # На случай если в state хранится list, приведем к списку обратно
        if col_index in selected_indices:
            selected_indices = [i for i in selected_indices if i != col_index]
        else:
            selected_indices.append(col_index)

    # Обновляем данные в FSM
    await state.update_data(selected_indices=selected_indices)

    # Обновляем клавиатуру в том же сообщении
    await callback_query.message.edit_reply_markup(
        reply_markup=get_column_selection_keyboard(header, selected_indices)
    )
    await callback_query.answer()


@setup_router.callback_query(
    StateFilter(GoogleFileForm.enter_lang_columns), F.data == "save_settings"
)
async def save_settings(callback_query, state: FSMContext):
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

        lang_column = UserVocabFileLangColumns(
            id=uuid.uuid4(),
            vocab_file_id=vocab_file.id,
            lang="lang_1",  # Здесь можно добавить логику определения языка по имени колонки
            column_index=col_index,
        )
        session.add(lang_column)
        await session.commit()
    await callback_query.message.answer("Настройки сохранены!")
    await state.clear()


@setup_router.message(StateFilter(None), Command("reset"))
async def reset_settings(message: Message, state: FSMContext):
    await state.clear()
    async with get_session() as session:
        user = await get_or_create_user(session, message.from_user)
        await delete_all_user_data(session, user.id)
    await message.answer("Настройки сброшены! Теперь вы можете начать заново.")


# ========== LEARNING ROUTER ==========


class TrainState(StatesGroup):
    gen_question = State()
    wait_user_answer = State()
    user_answered = State()


class TranContext(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        async with get_session() as session:
            data["orm_user"] = await get_or_create_user(session, event.from_user)
            data["session"] = session
            data["user_vocab_files"] = await get_user_vocab_files(
                session, data["orm_user"].id
            )
            if (
                not data["user_vocab_files"]
                or not data["user_vocab_files"][0].sheet_name
            ):
                await event.answer("Сначала настройте приложение командой /start")
                return
            dict_file = GoogleDictFile(
                google_sheet_id=data["user_vocab_files"][0].sheet_id
            )
            data["wp_ctx"] = WorldPairTrainStrategy(
                dict_file=dict_file,
                lang_from_col="A",
                lang_to_col="B",
                lang_from="English",
                lang_to="Russian",
            )
        return await handler(event, data)


learning_router.message.middleware(TranContext())


@learning_router.message(Command("train"))
async def cmd_start_train(message: Message, wp_ctx: WorldPairTrainStrategy):
    await message.answer("Начинаем тренировку!")
    await message.set_state(TrainState.gen_question)


@learning_router.message(StateFilter(TrainState.gen_question))
async def process_question(
    message: Message, wp_ctx: WorldPairTrainStrategy, state: FSMContext
):
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="Я не знаю", callback_data="dont_know_answer")
    )
    await message.answer(wp_ctx.next_word())
    await state.set_state(TrainState.wait_user_answer)


@learning_router.message(StateFilter(GoogleFileForm.enter_lang_columns))
async def cmd_learn(
    message: Message, state: FSMContext, wp_ctx: WorldPairTrainStrategy
):
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="Я не знаю", callback_data="dont_know_answer")
    )
    await message.answer(wp_ctx.next_word())


@learning_router.callback_query(F.data == "dont_know_answer")
async def process_dont_know(callback_query: Message, wp_ctx: WorldPairTrainStrategy):
    await callback_query.answer(wp_ctx.analyze_user_input("--"))


# ========== MAIN ==========
async def async_main():
    await create_all_tables()
    bot = Bot(token=Config().telegram_bot_token)
    dp = Dispatcher()

    dp.include_routers(setup_router, learning_router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


def main():
    import asyncio

    asyncio.run(async_main())


if __name__ == "__main__":
    main()
