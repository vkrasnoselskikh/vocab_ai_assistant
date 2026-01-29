from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, Message, TelegramObject
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_user_vocab_file_lang_columns, get_user_vocab_files
from ..google_dict_file import GoogleDictFile
from ..models import User, UserWordProgress
from ..training_strategies import WordTranslationStrategy, WorldPairTrainStrategy

learning_router = Router(name="learning")


class TrainState(StatesGroup):
    gen_question = State()
    wait_user_answer = State()
    user_answered = State()


class TrainingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        session: AsyncSession = data["session"]
        orm_user: User = data["orm_user"]

        user_vocab_files = await get_user_vocab_files(session, orm_user.id)
        if not user_vocab_files or not user_vocab_files[0].sheet_name:
            await event.answer("Сначала настройте приложение командой /start")
            return

        dict_file = GoogleDictFile(google_sheet_id=user_vocab_files[0].sheet_id)
        dict_file.sheet_name = user_vocab_files[0].sheet_name
        data["dict_file"] = dict_file

        lang_columns = await get_user_vocab_file_lang_columns(
            session, user_vocab_files[0].id
        )
        if len(lang_columns) != 2:
            await event.answer("Ошибка: неверные настройки колонок.")
            return

        if orm_user.training_mode == "word":
            strategy_class = WordTranslationStrategy
        else:
            strategy_class = WorldPairTrainStrategy

        data["training_strategy"] = strategy_class(
            dict_file=dict_file,
            lang_from=lang_columns[0].lang,
            lang_to=lang_columns[1].lang,
            lang_from_col=lang_columns[0].column_name,
            lang_to_col=lang_columns[1].column_name,
        )
        return await handler(event, data)


learning_router.message.middleware(TrainingMiddleware())


async def get_words_for_training(
    session: AsyncSession, user_id, dict_file: GoogleDictFile
):
    words_in_progress = (
        (
            await session.execute(
                select(UserWordProgress.word).where(
                    and_(
                        UserWordProgress.user_id == user_id,
                        UserWordProgress.is_passed == False,
                    )
                )
            )
        )
        .scalars()
        .all()
    )

    words_to_fetch = 10 - len(words_in_progress)
    if words_to_fetch > 0:
        new_words = [
            dict_file.get_random_row_excluding(exclude=words_in_progress)
            for _ in range(words_to_fetch)
        ]
        for word in new_words:
            session.add(
                UserWordProgress(user_id=user_id, word=word[0], is_passed=False)
            )
        await session.commit()
        return words_in_progress + [word[0] for word in new_words]
    return words_in_progress



@learning_router.message(Command("train"))
async def cmd_start_train(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    orm_user: User,
    dict_file: GoogleDictFile,
):
    words = await get_words_for_training(session, orm_user.id, dict_file)
    await state.update_data(words_for_training=words)
    await message.answer("Начинаем тренировку!")
    await state.set_state(TrainState.gen_question)
    await process_question(message, state)


@learning_router.message(StateFilter(TrainState.gen_question))
async def process_question(
    message: Message,
    state: FSMContext,
    training_strategy: WorldPairTrainStrategy,
):
    data = await state.get_data()
    words = data.get("words_for_training", [])
    if not words:
        # Fetch new words if the list is empty
        pass

    word_to, word_from = training_strategy.dict_file.get_random_row_excluding(
        exclude=words
    )
    await state.update_data(current_word=word_to)

    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="Я не знаю", callback_data="dont_know_answer")
    )
    await message.answer(
        training_strategy.next_word(word_to, word_from),
        reply_markup=builder.as_markup(),
    )
    await state.set_state(TrainState.wait_user_answer)


@learning_router.message(StateFilter(TrainState.wait_user_answer))
async def process_answer(
    message: Message,
    state: FSMContext,
    training_strategy: WorldPairTrainStrategy,
    session: AsyncSession,
    orm_user: User,
    dict_file: GoogleDictFile,
):
    user_input = message.text
    data = await state.get_data()
    current_word = data.get("current_word")
    response = training_strategy.analyze_user_input(user_input)
    await message.answer(response)

    if "correct" in response.lower():
        await session.execute(
            select(UserWordProgress)
            .where(
                and_(
                    UserWordProgress.user_id == orm_user.id,
                    UserWordProgress.word == current_word,
                )
            )
            .with_for_update()
        )
        progress = await session.scalar()
        if progress:
            progress.is_passed = True
            await session.commit()

        words = data.get("words_for_training", [])
        words.remove(current_word)
        if not words:
            words = await get_words_for_training(session, orm_user.id, dict_file)
        await state.update_data(words_for_training=words)

    await state.set_state(TrainState.gen_question)
    await process_question(message, state)


@learning_router.callback_query(F.data == "dont_know_answer")
async def process_dont_know(
    callback_query: Message,
    state: FSMContext,
    training_strategy: WorldPairTrainStrategy,
):
    response = training_strategy.analyze_user_input("--")
    await callback_query.message.answer(response)
    await state.set_state(TrainState.gen_question)
    await process_question(callback_query.message, state)
