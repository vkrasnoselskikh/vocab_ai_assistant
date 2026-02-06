import logging
import uuid
from typing import Any, Awaitable, Callable

from aiocache import Cache, cached
from aiogram import BaseMiddleware, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import KeyboardButton, Message
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import (
    get_user_vocab_file_lang_columns,
    get_user_vocab_files,
)
from ..google_dict_file import GoogleDictFile
from ..models import User
from ..training_strategies import (
    TrainStrategy,
    Word,
    WordTranslationSentenceStrategy,
    WorldPairTrainStrategy,
)

learning_router = Router(name="learning")
logger = logging.getLogger(__name__)


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

        data["training_strategy"] = await get_cached_training_strategy(
            orm_user.id,
            orm_user.training_mode or "pair",
            lang_columns[0].lang,
            lang_columns[1].lang,
        )
        return await handler(event, data)


learning_router.message.middleware(TrainingMiddleware())
learning_router.callback_query.middleware(TrainingMiddleware())


@learning_router.message(Command("train"))
async def cmd_start_train(
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

    from ..google_dict_file import _col_letter_to_index

    lang_cols = [lang_columns[0].column_name, lang_columns[1].column_name]
    unlearned_res = dict_file.get_unlearned_words(lang_cols=lang_cols, count=10)

    active_words: list[Word] = []
    for word_data, row_index in unlearned_res:
        word_from = word_data[_col_letter_to_index(lang_columns[0].column_name) - 1]
        word_to = word_data[_col_letter_to_index(lang_columns[1].column_name) - 1]
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
    await message.answer(
        f"Тренеруемся! Переведите слова с {lang_columns[0].lang} на {lang_columns[1].lang}!"
    )
    await process_question(message, state, training_strategy, dict_file)


@learning_router.message(TrainState.gen_question)
async def process_question(
    message: Message,
    state: FSMContext,
    training_strategy: TrainStrategy,
    dict_file: GoogleDictFile,
):
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

    response, _ = await training_strategy.analyze_user_input("--")
    await message.answer(response)

    # Ask a new question
    await process_question(message, state, training_strategy, dict_file)


@learning_router.message(StateFilter(TrainState.wait_user_answer))
async def process_answer(
    message: Message,
    state: FSMContext,
    training_strategy: TrainStrategy,
    dict_file: GoogleDictFile,
):
    user_input = message.text

    if user_input is None:
        return

    response, is_correct = await training_strategy.analyze_user_input(user_input)
    await message.answer(response)

    if is_correct:
        current_word = training_strategy.get_current_word()
        dict_file.update_word_status(current_word["row_index"], "learned")

    # Move to the next question
    await process_question(message, state, training_strategy, dict_file)
