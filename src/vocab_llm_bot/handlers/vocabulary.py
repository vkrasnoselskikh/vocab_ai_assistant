import json
import logging
from string import Template

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_user_vocab_file_lang_columns, get_user_vocab_files
from ..google_dict_file import GoogleDictFile
from ..llm import Message as LLMMessage
from ..llm import RoleMessage, get_completion
from ..models import User

logger = logging.getLogger(__name__)

vocabulary_router = Router(name="vocabulary")


class AddWordState(StatesGroup):
    waiting_for_phrase = State()


DETECT_AND_TRANSLATE_PROMPT = Template(
    """You are a dictionary assistant.
User languages: $lang1, $lang2.
User input: "$input_text"

Task:
1. Identify which language the input is in ($lang1 or $lang2).
2. Translate it to the other language.
3. Return a JSON object with keys corresponding to the column names: "$lang1" and "$lang2".

Example:
If languages are English, Russian and input is "Cat", output:
{ "English": "Cat", "Russian": "Кот" }

Output strictly JSON, no markdown.
"""
)


@vocabulary_router.message(Command("add"))
async def cmd_add_word(message: Message, state: FSMContext, session: AsyncSession, orm_user: User):
    user_vocab_files = await get_user_vocab_files(session, orm_user.id)
    if not user_vocab_files:
        await message.answer("Сначала настройте приложение командой /start")
        return

    await message.answer("Введите слово или фразу, которую хотите добавить:")
    await state.set_state(AddWordState.waiting_for_phrase)


@vocabulary_router.message(AddWordState.waiting_for_phrase, F.text)
async def process_new_word(
    message: Message, state: FSMContext, session: AsyncSession, orm_user: User
):
    user_input = message.text
    if not user_input:
        return

    user_vocab_files = await get_user_vocab_files(session, orm_user.id)
    if not user_vocab_files:
        await message.answer("Ошибка: словарь не найден.")
        await state.clear()
        return
    
    vocab_file = user_vocab_files[0]
    lang_columns = await get_user_vocab_file_lang_columns(session, vocab_file.id)
    
    if len(lang_columns) != 2:
        await message.answer("Ошибка: неверная конфигурация языков (должно быть 2).")
        await state.clear()
        return

    lang1 = lang_columns[0].column_name
    lang2 = lang_columns[1].column_name

    bot = message.bot
    if bot is None:
        raise RuntimeError("Message bot is not available")

    async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
        # Call LLM
        prompt_text = DETECT_AND_TRANSLATE_PROMPT.substitute(
            lang1=lang1, lang2=lang2, input_text=user_input
        )
        messages: list[LLMMessage] = [{"role": RoleMessage.user, "content": prompt_text}]

        try:
            response_text = await get_completion(messages)
            # Remove markdown code blocks if present
            cleaned_text = (
                response_text.replace("```json", "").replace("```", "").strip()
            )
            word_data = json.loads(cleaned_text)
        except Exception as e:
            logger.error(f"LLM Error: {e}")
            await message.answer("Не удалось обработать запрос. Попробуйте еще раз.")
            return

        # Validate JSON keys
        if lang1 not in word_data or lang2 not in word_data:
            logger.error(f"Invalid LLM response keys: {word_data.keys()}")
            await message.answer(
                "Не удалось определить перевод. Попробуйте переформулировать."
            )
            return

        # Save to Google Sheet
        try:
            dict_file = GoogleDictFile(vocab_file.sheet_id)
            if vocab_file.sheet_name:
                dict_file.sheet_name = vocab_file.sheet_name
            else:
                 # Should not happen if configured correctly, but safe fallback
                 sheets = dict_file.get_sheets()
                 if sheets:
                     dict_file.sheet_name = sheets[0].get("properties", {}).get("title", "Sheet1")

            dict_file.add_word(word_data)

            await message.answer(
                f"✅ Добавлено:\n{lang1}: {word_data.get(lang1)}\n{lang2}: {word_data.get(lang2)}"
            )
        except Exception as e:
            logger.error(f"Google Sheet Error: {e}")
            await message.answer(f"Ошибка при сохранении в таблицу: {e}")

    await state.clear()
