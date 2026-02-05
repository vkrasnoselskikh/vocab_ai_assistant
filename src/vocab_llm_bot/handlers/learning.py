from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import (
    get_user_vocab_file_lang_columns,
    get_user_vocab_files,
)
from ..google_dict_file import GoogleDictFile
from ..models import User
from ..training_strategies import WordTranslationStrategy, WorldPairTrainStrategy

learning_router = Router(name="learning")


class TrainState(StatesGroup):
    gen_question = State()
    wait_user_answer = State()


class TrainingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:  # type: ignore
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


learning_router.message.middleware(TrainingMiddleware())  # type: ignore


@learning_router.message(Command("train"))
async def cmd_start_train(
    message: Message,
    state: FSMContext,
):
    await message.answer("Начинаем тренировку!")
    await state.set_state(TrainState.gen_question)
    # Redirect to process_question
    await process_question(message, state, data=await state.get_data())


@learning_router.message(StateFilter(TrainState.gen_question))
async def process_question(
    message: Message,
    state: FSMContext,
    training_strategy: WorldPairTrainStrategy,
    dict_file: GoogleDictFile,
):
    word_data, row_index = dict_file.get_random_unlearned_word()

    if word_data is None:
        await message.answer("Поздравляю! Вы выучили все слова! 🎉")
        await state.clear()
        return

    # Assuming word_from is in the first column and word_to is in the second
    word_from, word_to = word_data[0], word_data[1]

    await state.update_data(current_word_data=word_data, current_row_index=row_index)

    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="Я не знаю", callback_data="dont_know_answer")
    )
    await message.answer(
        await training_strategy.next_word(word_to=word_to, word_from=word_from),
        reply_markup=builder.as_markup(),
    )
    await state.set_state(TrainState.wait_user_answer)


@learning_router.message(StateFilter(TrainState.wait_user_answer))
async def process_answer(
    message: Message,
    state: FSMContext,
    training_strategy: WorldPairTrainStrategy,
    dict_file: GoogleDictFile,
):
    user_input = message.text
    data = await state.get_data()
    current_word_data = data.get("current_word_data")
    current_row_index = data.get("current_row_index")

    if not current_word_data or not current_row_index:
        await message.answer("Что-то пошло не так, давайте начнем заново.")
        await state.clear()
        return

    # Assuming the correct answer is the second element in the pair
    correct_answer = current_word_data[1]

    if user_input == "Я не знаю":
        # Using analyze_user_input to get a "don't know" response from the LLM
        response = await training_strategy.analyze_user_input("I dont know")
        await message.answer(f"{response}\n\nПравильный ответ: {correct_answer}")
        # Ask the same question again
        await state.set_state(TrainState.gen_question)
        await process_question(message, state, training_strategy, dict_file)
        return

    response = await training_strategy.analyze_user_input(user_input)
    await message.answer(response)

    if "correct" in response.lower():
        status_col_info = dict_file.get_status_column_info()
        if status_col_info:
            _, status_col_letter = status_col_info
            dict_file.update_word_status(
                current_row_index, status_col_letter, "learned"
            )
        else:
            # Log or notify user that 'Status' column is missing
            await message.answer("Внимание: колонка 'Status' не найдена в таблице.")

    # Move to the next question
    await state.set_state(TrainState.gen_question)
    await process_question(message, state, training_strategy, dict_file)


@learning_router.callback_query(F.data == "dont_know_answer")
async def process_dont_know(
    callback_query: Message,
    state: FSMContext,
    training_strategy: WorldPairTrainStrategy,
    dict_file: GoogleDictFile,
):
    data = await state.get_data()
    current_word_data = data.get("current_word_data")

    if not current_word_data:
        await callback_query.answer("Что-то пошло не так, давайте начнем заново.")
        await state.clear()
        return

    correct_answer = current_word_data[1]
    response = await training_strategy.analyze_user_input("--")
    await callback_query.message.answer(
        f"{response}\n\nПравильный ответ: {correct_answer}"
    )

    # Ask a new question
    await state.set_state(TrainState.gen_question)
    await process_question(callback_query, state, training_strategy, dict_file)
