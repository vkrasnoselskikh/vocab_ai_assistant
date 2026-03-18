import uuid

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
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
    get_user_vocab_files,
)
from ..google_dict_file import GoogleDictFile
from ..models import User, UserVocabFileLangColumns

setup_router = Router(name="setup")


def get_bot_email():
    return GoogleServiceAccount().get_client_email()

START_MESSAGE = """\
<b>Начнем!</b>
Вам понадобится файл с вашим словарем в Google Sheets.
Он должен выглядеть как лист с двумя колонками.
В качестве первой строки должны быть названия языков, которые вы хотите учить. 

Например:
<code>Русский   | Английский
----------+-----------
Кошка     | cat
Собака    | dog
Дом       | house</code>
"""

GIVE_ME_ACCESS_MESSAGE = f"""\
Чтобы начать заниматься, предоставьте доступ к вашему Google Sheet файлу (c правом на редактирование) на эту почту:
<pre><code>{get_bot_email()}</code></pre>
"""
GIVE_ME_LINK_MESSAGE = """Вставьте ссылку на этот файл ниже:"""


# FSM только для настройки
class GoogleFileForm(StatesGroup):
    enter_link = State()
    enter_sheet_name = State()
    enter_lang_columns = State()
    



@setup_router.message(Command("start"))
async def cmd_start(
    message: Message, state: FSMContext, session: AsyncSession, orm_user: User
):
    await state.clear()
    await delete_all_user_data(session, orm_user.id)
    orm_user.training_mode = None
    session.add(orm_user)
    await session.commit()

    await message.answer(text=START_MESSAGE, parse_mode="HTML")
    await message.answer(text=GIVE_ME_ACCESS_MESSAGE, parse_mode="HTML")
    await message.answer(text=GIVE_ME_LINK_MESSAGE)
    await state.set_state(GoogleFileForm.enter_link)


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
    if callback_query.message is None:
        await callback_query.answer()
        return

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

    # Удаляем сообщение с кнопками выбора листа после клика.
    try:
        await callback_query.message.delete()
    except TelegramBadRequest:
        pass

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
    if callback_query.message is None:
        await callback_query.answer("Ошибка: сообщение не найдено.", show_alert=True)
        return

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

    # Удаляем сообщение с кнопками выбора колонок после сохранения.
    try:
        await callback_query.message.delete()
    except TelegramBadRequest:
        pass

    await callback_query.message.answer(
        "Колонки успешно сохранены! "
        "Теперь вы можете начать тренировку с помощью команды /train"
    )
    await callback_query.answer()
    await state.clear()
