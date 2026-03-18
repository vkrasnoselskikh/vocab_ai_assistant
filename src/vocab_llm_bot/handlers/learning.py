import logging
import uuid
from typing import Any, Awaitable, Callable

from aiocache import Cache, cached
from aiogram import BaseMiddleware, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, KeyboardButton, Message
from aiogram.utils.chat_action import ChatActionSender
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import (
    get_user_vocab_file_lang_columns,
    get_user_vocab_files,
)
from ..google_dict_file import GoogleDictFile
from ..models import User, UserVocabFileLangColumns
from ..training_strategies import (
    TrainStrategy,
    Word,
    WordTranslationSentenceStrategy,
    WorldPairTrainStrategy,
)

learning_router = Router(name="learning")
logger = logging.getLogger(__name__)


def parse_training_mode(
    raw_training_mode: str | None,
) -> tuple[str, str | None, str | None]:
    if raw_training_mode is None:
        return "word", None, None

    chunks = raw_training_mode.split("|")
    if len(chunks) == 3 and chunks[0] in {"word", "sentence"}:
        return chunks[0], chunks[1], chunks[2]

    if raw_training_mode in {"word", "sentence"}:
        return raw_training_mode, None, None

    return "word", None, None


def get_direction_keyboard(
    mode: str, lang_columns: list[UserVocabFileLangColumns]
):
    first_lang = lang_columns[0]
    second_lang = lang_columns[1]
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=f"{first_lang.lang} -> {second_lang.lang}",
            callback_data=(
                f"train_direction:{mode}:{first_lang.column_name}:{second_lang.column_name}"
            ),
        )
    )
    builder.row(
        InlineKeyboardButton(
            text=f"{second_lang.lang} -> {first_lang.lang}",
            callback_data=(
                f"train_direction:{mode}:{second_lang.column_name}:{first_lang.column_name}"
            ),
        )
    )
    return builder.as_markup()


def get_training_mode_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="Перевод слов",
            callback_data="train_select_mode:word",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="Перевод предложений",
            callback_data="train_select_mode:sentence",
        )
    )
    return builder.as_markup()


def resolve_lang_columns_by_direction(
    lang_columns: list[UserVocabFileLangColumns],
    raw_training_mode: str | None,
) -> tuple[str, UserVocabFileLangColumns, UserVocabFileLangColumns]:
    mode, from_col, to_col = parse_training_mode(raw_training_mode)
    col_by_name = {lang_col.column_name: lang_col for lang_col in lang_columns}

    if from_col and to_col and from_col in col_by_name and to_col in col_by_name:
        return mode, col_by_name[from_col], col_by_name[to_col]

    return mode, lang_columns[0], lang_columns[1]


@cached(cache=Cache.MEMORY, ttl=900)
async def get_cached_dict_file(sheet_id: str, sheet_name: str) -> GoogleDictFile:
    dict_file = GoogleDictFile(google_sheet_id=sheet_id)
    dict_file.sheet_name = sheet_name
    return dict_file


@cached(cache=Cache.MEMORY, ttl=900)
async def get_cached_training_strategy(
    user_id: uuid.UUID, training_mode: str, lang_from: str, lang_to: str
) -> TrainStrategy:
    if training_mode == "word":
        strategy_class = WorldPairTrainStrategy
    else:
        strategy_class = WordTranslationSentenceStrategy

    return strategy_class(
        lang_from=lang_from,
        lang_to=lang_to,
    )


class TrainState(StatesGroup):
    gen_question = State()
    wait_user_answer = State()


class TrainingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: dict[str, Any],
    ) -> Any:
        session: AsyncSession = data["session"]
        orm_user: User = data["orm_user"]

        user_vocab_files = await get_user_vocab_files(session, orm_user.id)
        if not user_vocab_files or not user_vocab_files[0].sheet_name:
            if hasattr(event, "answer"):
                await event.answer("Сначала настройте приложение командой /start")
            return

        dict_file = await get_cached_dict_file(
            user_vocab_files[0].sheet_id, user_vocab_files[0].sheet_name
        )
        data["dict_file"] = dict_file

        lang_columns = await get_user_vocab_file_lang_columns(
            session, user_vocab_files[0].id
        )
        if len(lang_columns) != 2:
            if hasattr(event, "answer"):
                await event.answer("Ошибка: неверные настройки колонок.")
            return

        mode, lang_from, lang_to = resolve_lang_columns_by_direction(
            list(lang_columns), orm_user.training_mode
        )
        data["training_strategy"] = await get_cached_training_strategy(
            orm_user.id,
            mode,
            lang_from.lang,
            lang_to.lang,
        )
        return await handler(event, data)


learning_router.message.middleware(TrainingMiddleware())
learning_router.callback_query.middleware(TrainingMiddleware())


@learning_router.message(Command("train"))
async def cmd_start_train(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    orm_user: User,
):
    await state.clear()

    user_vocab_files = await get_user_vocab_files(session, orm_user.id)
    if not user_vocab_files or not user_vocab_files[0].sheet_name:
        await message.answer("Сначала настройте приложение командой /start")
        return

    lang_columns = await get_user_vocab_file_lang_columns(session, user_vocab_files[0].id)
    if not lang_columns or len(lang_columns) != 2:
        await message.answer("Ошибка: неверные настройки колонок.")
        return

    await state.clear()
    await message.answer(
        "Выберите режим тренировки:",
        reply_markup=get_training_mode_keyboard(),
    )


async def start_training_session(
    message: Message,
    state: FSMContext,
    dict_file: GoogleDictFile,
    training_strategy: TrainStrategy,
    session: AsyncSession,
    orm_user: User,
):
    await message.answer("Читаю слова из вашего словаря...")

    user_vocab_files = await get_user_vocab_files(session, orm_user.id)
    if not user_vocab_files:
        await message.answer("Ошибка: файл не найден.")
        return

    lang_columns = await get_user_vocab_file_lang_columns(
        session, user_vocab_files[0].id
    )
    if not lang_columns or len(lang_columns) != 2:
        await message.answer("Ошибка: неверные настройки колонок.")
        return

    mode, lang_from, lang_to = resolve_lang_columns_by_direction(
        list(lang_columns), orm_user.training_mode
    )

    from ..google_dict_file import _col_letter_to_index

    lang_cols = [lang_from.column_name, lang_to.column_name]
    unlearned_res = dict_file.get_unlearned_words(lang_cols=lang_cols, count=10)

    active_words: list[Word] = []
    for word_data, row_index in unlearned_res:
        word_from = word_data[_col_letter_to_index(lang_from.column_name) - 1]
        word_to = word_data[_col_letter_to_index(lang_to.column_name) - 1]
        active_words.append(
            {
                "word_from": word_from,
                "word_to": word_to,
                "row_index": row_index,
            }
        )

    if not active_words:
        await message.answer("Поздравляю! Вы выучили все слова! 🎉")
        await state.clear()
        return

    training_strategy.set_words(active_words)
    if mode == "sentence":
        intro_text = (
            f"Начнем тренировку! Переводите предложения с "
            f"{lang_from.lang} на {lang_to.lang}."
        )
    else:
        intro_text = (
            f"Начнем тренировку! Переведите слова с {lang_from.lang} "
            f"на {lang_to.lang}!"
        )

    await message.answer(intro_text)
    await process_question(message, state, training_strategy, dict_file)


@learning_router.callback_query(F.data.startswith("train_select_mode:"))
async def process_train_mode_selection(
    callback_query,
    session: AsyncSession,
    orm_user: User,
):
    if callback_query.message is None:
        await callback_query.answer()
        return

    mode = callback_query.data.split(":")[1]
    user_vocab_files = await get_user_vocab_files(session, orm_user.id)
    if not user_vocab_files:
        await callback_query.message.answer("Ошибка: файл не найден.")
        await callback_query.answer()
        return

    lang_columns = await get_user_vocab_file_lang_columns(session, user_vocab_files[0].id)
    if len(lang_columns) != 2:
        await callback_query.message.answer("Ошибка: неверные настройки колонок.")
        await callback_query.answer()
        return

    await callback_query.message.answer(
        "Выберите направление перевода:",
        reply_markup=get_direction_keyboard(mode, list(lang_columns)),
    )
    await callback_query.answer()


@learning_router.message(TrainState.gen_question)
async def process_question(
    message: Message,
    state: FSMContext,
    training_strategy: TrainStrategy,
    dict_file: GoogleDictFile,
):
    bot = message.bot
    if bot is None:
        raise RuntimeError("Message bot is not available")
    async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
        question_text = await training_strategy.next_word()

    if question_text is None:
        await message.answer("Поздравляю! Вы выучили все слова! 🎉")
        await state.clear()
        return

    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="Я не знаю", callback_data="dont_know_answer"))

    await message.answer(
        question_text,
        reply_markup=builder.as_markup(
            input_field_placeholder="Напишите перевод:", resize_keyboard=True
        ),
    )
    await state.set_state(TrainState.wait_user_answer)


@learning_router.message(
    StateFilter(TrainState.wait_user_answer),
    F.text == "Я не знаю",
)
async def process_dont_know(
    message: Message,
    orm_user: User,
    state: FSMContext,
    training_strategy: TrainStrategy,
    dict_file: GoogleDictFile,
):
    current_word = training_strategy.get_current_word()

    logger.info(f"User {orm_user.id} skipped word: {current_word.get('word_from')}")

    bot = message.bot
    if bot is None:
        raise RuntimeError("Message bot is not available")
    async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
        response, _ = await training_strategy.analyze_user_input("--")
    await message.answer(response)

    # Ask a new question
    await process_question(message, state, training_strategy, dict_file)


@learning_router.message(
    StateFilter(TrainState.wait_user_answer), F.text, ~F.text.startswith("/")
)
async def process_answer(
    message: Message,
    state: FSMContext,
    training_strategy: TrainStrategy,
    dict_file: GoogleDictFile,
):
    user_input = message.text

    if user_input is None:
        return

    bot = message.bot
    if bot is None:
        raise RuntimeError("Message bot is not available")
    async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
        response, is_correct = await training_strategy.analyze_user_input(user_input)
    await message.answer(response)

    if is_correct:
        current_word = training_strategy.get_current_word()
        dict_file.update_word_status(current_word["row_index"], "learned")

    # Move to the next question
    await process_question(message, state, training_strategy, dict_file)


@learning_router.callback_query(F.data.startswith("train_direction:"))
async def process_train_direction_selection(
    callback_query,
    state: FSMContext,
    dict_file: GoogleDictFile,
    session: AsyncSession,
    orm_user: User,
):
    _, mode, lang_from_col, lang_to_col = callback_query.data.split(":", 3)
    orm_user.training_mode = f"{mode}|{lang_from_col}|{lang_to_col}"
    session.add(orm_user)
    await session.commit()
    await callback_query.answer()

    if callback_query.message is None:
        return

    lang_columns = await get_user_vocab_file_lang_columns(
        session, (await get_user_vocab_files(session, orm_user.id))[0].id
    )
    _, lang_from, lang_to = resolve_lang_columns_by_direction(
        list(lang_columns), orm_user.training_mode
    )
    training_strategy = await get_cached_training_strategy(
        orm_user.id,
        mode,
        lang_from.lang,
        lang_to.lang,
    )

    await start_training_session(
        callback_query.message,
        state,
        dict_file,
        training_strategy,
        session,
        orm_user,
    )
