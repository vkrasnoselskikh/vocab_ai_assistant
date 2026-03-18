from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, Chat, User as AiogramUser

from vocab_llm_bot.handlers.vocabulary import cmd_add_word, process_new_word, AddWordState
from vocab_llm_bot.models import User, UserVocabFile, UserVocabFileLangColumns

@pytest.fixture
def mock_message():
    message = AsyncMock(spec=Message)
    message.text = "test phrase"
    message.chat = MagicMock(spec=Chat)
    message.chat.id = 123
    message.from_user = MagicMock(spec=AiogramUser)
    message.from_user.id = 456
    message.bot = MagicMock()
    # Explicitly make answer an AsyncMock
    message.answer = AsyncMock()
    return message

@pytest.fixture
def mock_state():
    state = AsyncMock(spec=FSMContext)
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    return state

@pytest.fixture
def mock_session():
    return AsyncMock()

@pytest.fixture
def mock_user():
    user = MagicMock(spec=User)
    user.id = "user-uuid"
    return user

@pytest.mark.asyncio
async def test_cmd_add_word_success(mock_message, mock_state, mock_session, mock_user):
    with patch("vocab_llm_bot.handlers.vocabulary.get_user_vocab_files", new_callable=AsyncMock) as mock_get_files:
        mock_get_files.return_value = [MagicMock()]
        
        await cmd_add_word(mock_message, mock_state, mock_session, mock_user)
        
        mock_message.answer.assert_called_with("Введите слово или фразу, которую хотите добавить:")
        mock_state.set_state.assert_called_with(AddWordState.waiting_for_phrase)

@pytest.mark.asyncio
async def test_cmd_add_word_no_files(mock_message, mock_state, mock_session, mock_user):
    with patch("vocab_llm_bot.handlers.vocabulary.get_user_vocab_files", new_callable=AsyncMock) as mock_get_files:
        mock_get_files.return_value = []
        
        await cmd_add_word(mock_message, mock_state, mock_session, mock_user)
        
        mock_message.answer.assert_called_with("Сначала настройте приложение командой /start")
        mock_state.set_state.assert_not_called()

@pytest.mark.asyncio
async def test_process_new_word_success(mock_message, mock_state, mock_session, mock_user):
    # Setup mocks
    vocab_file = MagicMock(spec=UserVocabFile)
    vocab_file.id = "file-uuid"
    vocab_file.sheet_id = "sheet-id"
    vocab_file.sheet_name = "Sheet1"
    
    col1 = MagicMock(spec=UserVocabFileLangColumns)
    col1.column_name = "English"
    col2 = MagicMock(spec=UserVocabFileLangColumns)
    col2.column_name = "Russian"
    
    with patch("vocab_llm_bot.handlers.vocabulary.get_user_vocab_files", new_callable=AsyncMock) as mock_get_files, \
         patch("vocab_llm_bot.handlers.vocabulary.get_user_vocab_file_lang_columns", new_callable=AsyncMock) as mock_get_cols, \
         patch("vocab_llm_bot.handlers.vocabulary.get_completion", new_callable=AsyncMock) as mock_llm, \
         patch("vocab_llm_bot.handlers.vocabulary.GoogleDictFile") as mock_gdf_cls, \
         patch("vocab_llm_bot.handlers.vocabulary.ChatActionSender") as mock_sender:
        
        mock_get_files.return_value = [vocab_file]
        mock_get_cols.return_value = [col1, col2]
        
        # Mock LLM response
        mock_llm.return_value = '```json\n{"English": "Cat", "Russian": "Кот"}\n```'
        
        # Mock GoogleDictFile instance
        mock_gdf_instance = MagicMock()
        mock_gdf_cls.return_value = mock_gdf_instance
        
        await process_new_word(mock_message, mock_state, mock_session, mock_user)
        
        # Verify LLM call
        mock_llm.assert_called_once()
        
        # Verify Google Sheet Add
        mock_gdf_instance.add_word.assert_called_once_with({"English": "Cat", "Russian": "Кот"})
        
        # Verify Success Message
        args, _ = mock_message.answer.call_args
        assert "✅ Добавлено" in args[0]
        assert "English: Cat" in args[0]
        assert "Russian: Кот" in args[0]
        
        # Verify State Clear
        mock_state.clear.assert_called_once()

