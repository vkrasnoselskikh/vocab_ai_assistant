import uuid

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import GoogleServiceAccount
from ..database import (
    create_uesr_vocab_file,
    delete_all_user_data,
    get_or_create_user,
    get_session,
    get_user_vocab_file_lang_columns,
    get_user_vocab_files,
)
from ..google_dict_file import GoogleDictFile
from ..models import User, UserVocabFileLangColumns

setup_router = Router(name="setup")


def get_bot_email():
    return GoogleServiceAccount().get_client_email()


# FSM только для настройки
class GoogleFileForm(StatesGroup):
    enter_link = State()
    enter_sheet_name = State()
    enter_lang_columns = State()
    select_training_mode = State()
    select_translation_direction = State()


@setup_router.message(StateFilter(None), Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    async with get_session() as session:
        user = await get_or_create_user(session, message.from_user)
        user_vocab_files = await get_user_vocab_files(session, user.id)

        if len(user_vocab_files) == 0:
            await message.answer(
                text=(
                    "Давайте настроем ваш словарь.\n"
                    "Предоставьте доступ к вашему Google Sheet файлу на мою сервисную почту: "
                    + get_bot_email()
                    + "\n. Это нужно для взаимодействия с вашим словарем."
                    + "Как только вы предоставите доступ, пришлите в ответ ссылку на файл."
                )
            )
            await state.set_state(GoogleFileForm.enter_link)
        else:
            await message.answer(
                text="У вас уже все настроено. Начните учить слова командой /train"
            )


@setup_router.message(StateFilter(GoogleFileForm.enter_link), F.text)
async def process_file_link(
    message: Message, state: FSMContext, session: AsyncSession, orm_user: User
):
    if message.text is None:
        await message.answer("Пожалуйста, введите ссылку на файл:")
        return

    link = message.text.strip()
    # Извлекаем ID файла из ссылки
    if "spreadsheets/d/" in link:
        google_file_id = link.split("spreadsheets/d/")[1].split("/")[0]
    else:
        google_file_id = link

    await create_uesr_vocab_file(
        session, user_id=orm_user.id, google_file_id=google_file_id
    )

    # Получаем список листов
    google_dict_file = GoogleDictFile(google_sheet_id=google_file_id)
    sheets = google_dict_file.get_sheets()

    if not sheets:
        await message.answer(
            "Не удалось получить доступ к файлу или в нём нет листов. Проверьте права доступа."
        )
        return

    builder = InlineKeyboardBuilder()
    for sheet in sheets:
        title = sheet.get("properties", {}).get("title", "Unknown")
        builder.row(
            InlineKeyboardButton(text=title, callback_data=f"select_sheet:{title}")
        )

    await state.set_state(GoogleFileForm.enter_sheet_name)
    await message.answer(
        "Отлично! Теперь выберите лист со словарём из списка ниже:",
        reply_markup=builder.as_markup(),
    )


@setup_router.callback_query(
    StateFilter(GoogleFileForm.enter_sheet_name), F.data.startswith("select_sheet:")
)
async def process_sheet_selection(
    callback_query, state: FSMContext, session: AsyncSession, orm_user: User
):
    sheet_name = callback_query.data.split(":")[1]

    user_vocab_files = await get_user_vocab_files(session, orm_user.id)
    if not user_vocab_files:
        await callback_query.message.answer("Ошибка: файл не найден.")
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
    await callback_query.message.answer(
        f"Вы выбрали лист: {sheet_name}\nТеперь выберите языковые колонки:",
        reply_markup=get_column_selection_keyboard(header, []),
    )
    await callback_query.answer()


def get_column_selection_keyboard(
    header_list: list[tuple[str, int, str]], selected_indices: list[int]
):
    builder = InlineKeyboardBuilder()
    for idx, (col_name, _, _) in enumerate(header_list):
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
async def save_settings(
    callback_query, state: FSMContext, session: AsyncSession, orm_user: User
):
    data = await state.get_data()
    selected_indices = data.get("selected_indices", [])
    header = data.get("header", [])

    if len(selected_indices) != 2:
        await callback_query.answer(
            "Пожалуйста, выберите две колонки в которых вы храните слова и их переводы.",
            show_alert=True,
        )
        return

    user_vocab_files = await get_user_vocab_files(session, orm_user.id)
    if not user_vocab_files:
        await callback_query.message.answer("Ошибка: файл не найден.")
        return
    vocab_file = user_vocab_files[0]

    for index in selected_indices:
        lang_column = UserVocabFileLangColumns(
            id=uuid.uuid4(),
            vocab_file_id=vocab_file.id,
            lang=header[index][0],
            column_name=header[index][2],
        )
        session.add(lang_column)
    await session.commit()
    await callback_query.answer("Колонки успешно сохранены!")
    await state.set_state(GoogleFileForm.select_training_mode)
    await select_training_mode(callback_query.message, state, session, orm_user)


@setup_router.message(Command("setup"))
async def select_training_mode(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    orm_user: User,
):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="Перевод слов", callback_data="select_training_mode:word"
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="Перевод предложений", callback_data="select_training_mode:sentence"
        )
    )
    await message.answer(
        "Выберите режим тренировки:",
        reply_markup=builder.as_markup(),
    )
    await state.set_state(GoogleFileForm.select_training_mode)


@setup_router.callback_query(
    F.data.startswith("select_training_mode:"),
)
async def process_training_mode_selection(
    callback_query, state: FSMContext, session: AsyncSession, orm_user: User
):
    mode = callback_query.data.split(":")[1]
    user_vocab_files = await get_user_vocab_files(session, orm_user.id)
    if not user_vocab_files:
        await callback_query.message.answer("Ошибка: файл не найден.")
        return
    lang_columns = await get_user_vocab_file_lang_columns(session, user_vocab_files[0].id)
    if len(lang_columns) != 2:
        await callback_query.message.answer("Ошибка: неверные настройки колонок.")
        return

    first_lang = lang_columns[0]
    second_lang = lang_columns[1]
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=f"{first_lang.lang} -> {second_lang.lang}",
            callback_data=(
                f"select_translation_direction:"
                f"{mode}:{first_lang.column_name}:{second_lang.column_name}"
            ),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=f"{second_lang.lang} -> {first_lang.lang}",
            callback_data=(
                f"select_translation_direction:"
                f"{mode}:{second_lang.column_name}:{first_lang.column_name}"
            ),
        )
    )

    await state.set_state(GoogleFileForm.select_translation_direction)
    await callback_query.message.answer(
        "Выберите направление перевода:",
        reply_markup=builder.as_markup(),
    )
    await callback_query.answer()


@setup_router.callback_query(
    StateFilter(GoogleFileForm.select_translation_direction),
    F.data.startswith("select_translation_direction:"),
)
async def process_translation_direction_selection(
    callback_query, state: FSMContext, session: AsyncSession, orm_user: User
):
    _, mode, lang_from_col, lang_to_col = callback_query.data.split(":", 3)
    orm_user.training_mode = f"{mode}|{lang_from_col}|{lang_to_col}"
    session.add(orm_user)
    await session.commit()
    await state.clear()

    await callback_query.answer()
    await callback_query.message.answer(
        "Направление перевода сохранено. Начните тренировку командой /train."
    )


@setup_router.message(Command("reset"))
async def reset_settings(
    message: Message, state: FSMContext, session: AsyncSession, orm_user: User
):
    await state.clear()
    await delete_all_user_data(session, orm_user.id)
    await message.answer(
        "Настройки сброшены! Теперь вы можете начать все заново. /start"
    )
