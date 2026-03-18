from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.types import Chat, Message, User as AiogramUser

from vocab_llm_bot.handlers.setup import (
    GIVE_ME_ACCESS_MESSAGE,
    GIVE_ME_LINK_MESSAGE,
    START_MESSAGE,
    GoogleFileForm,
    cmd_start,
    fallback_no_state_message,
    process_sheet_selection,
    save_settings,
)
from vocab_llm_bot.models import User, UserVocabFile


@pytest.fixture
def mock_message() -> AsyncMock:
    message = AsyncMock(spec=Message)
    message.chat = MagicMock(spec=Chat)
    message.chat.id = 123
    message.from_user = MagicMock(spec=AiogramUser)
    message.from_user.id = 456
    message.answer = AsyncMock()
    return message


@pytest.fixture
def mock_state() -> AsyncMock:
    state = AsyncMock(spec=FSMContext)
    state.clear = AsyncMock()
    state.set_state = AsyncMock()
    return state


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def mock_user() -> MagicMock:
    user = MagicMock(spec=User)
    user.id = "user-uuid"
    user.training_mode = "word|A:B"
    return user


@pytest.mark.asyncio
async def test_cmd_start_restarts_setup_from_any_state(
    mock_message: AsyncMock,
    mock_state: AsyncMock,
    mock_session: AsyncMock,
    mock_user: MagicMock,
) -> None:
    with patch(
        "vocab_llm_bot.handlers.setup.delete_all_user_data", new_callable=AsyncMock
    ) as mock_delete_user_data:
        await cmd_start(mock_message, mock_state, mock_session, mock_user)

    mock_state.clear.assert_called_once()
    mock_delete_user_data.assert_called_once_with(mock_session, mock_user.id)
    assert mock_user.training_mode is None
    mock_session.add.assert_called_once_with(mock_user)
    mock_session.commit.assert_called_once()
    mock_state.set_state.assert_called_once_with(GoogleFileForm.enter_link)
    assert mock_message.answer.call_count == 3
    call_texts = [call.kwargs["text"] for call in mock_message.answer.call_args_list]
    assert call_texts == [START_MESSAGE, GIVE_ME_ACCESS_MESSAGE, GIVE_ME_LINK_MESSAGE]


@pytest.mark.asyncio
async def test_process_sheet_selection_deletes_buttons_message(
    mock_state: AsyncMock, mock_session: AsyncMock, mock_user: MagicMock
) -> None:
    callback_query = AsyncMock()
    callback_query.data = "select_sheet:Sheet1"
    callback_query.message = AsyncMock(spec=Message)
    callback_query.message.answer = AsyncMock()
    callback_query.message.delete = AsyncMock()
    callback_query.answer = AsyncMock()

    vocab_file = MagicMock(spec=UserVocabFile)
    vocab_file.sheet_id = "sheet-id"

    with patch(
        "vocab_llm_bot.handlers.setup.get_user_vocab_files", new_callable=AsyncMock
    ) as mock_get_files, patch(
        "vocab_llm_bot.handlers.setup.GoogleDictFile"
    ) as mock_gdf_cls:
        mock_get_files.return_value = [vocab_file]
        mock_gdf_instance = MagicMock()
        mock_gdf_instance.get_header.return_value = [("English", 1, "A")]
        mock_gdf_cls.return_value = mock_gdf_instance

        await process_sheet_selection(callback_query, mock_state, mock_session, mock_user)

    callback_query.message.delete.assert_called_once()
    callback_query.message.answer.assert_called_once()
    mock_state.set_state.assert_called_once_with(GoogleFileForm.enter_lang_columns)


@pytest.mark.asyncio
async def test_save_settings_deletes_buttons_message(
    mock_state: AsyncMock, mock_session: AsyncMock, mock_user: MagicMock
) -> None:
    callback_query = AsyncMock()
    callback_query.data = "save_settings"
    callback_query.message = AsyncMock(spec=Message)
    callback_query.message.answer = AsyncMock()
    callback_query.message.delete = AsyncMock()
    callback_query.answer = AsyncMock()

    mock_state.get_data = AsyncMock(
        return_value={
            "selected_indices": [0, 1],
            "header": [("English", 1, "A"), ("Russian", 2, "B")],
        }
    )

    vocab_file = MagicMock(spec=UserVocabFile)
    vocab_file.id = "file-uuid"

    with patch(
        "vocab_llm_bot.handlers.setup.get_user_vocab_files", new_callable=AsyncMock
    ) as mock_get_files:
        mock_get_files.return_value = [vocab_file]
        await save_settings(callback_query, mock_state, mock_session, mock_user)

    callback_query.message.delete.assert_called_once()
    callback_query.message.answer.assert_called_once()
    callback_query.answer.assert_called_once()
    mock_state.clear.assert_called_once()


@pytest.mark.asyncio
async def test_fallback_no_state_message_suggests_train_for_configured_user(
    mock_message: AsyncMock, mock_session: AsyncMock, mock_user: MagicMock
) -> None:
    vocab_file = MagicMock(spec=UserVocabFile)
    vocab_file.sheet_name = "Sheet1"

    with patch(
        "vocab_llm_bot.handlers.setup.get_user_vocab_files", new_callable=AsyncMock
    ) as mock_get_files:
        mock_get_files.return_value = [vocab_file]
        await fallback_no_state_message(mock_message, mock_session, mock_user)

    mock_message.answer.assert_called_once_with(
        "Похоже, текущая сессия сбросилась. Начните тренировку командой /train"
    )


@pytest.mark.asyncio
async def test_fallback_no_state_message_suggests_start_without_config(
    mock_message: AsyncMock, mock_session: AsyncMock, mock_user: MagicMock
) -> None:
    with patch(
        "vocab_llm_bot.handlers.setup.get_user_vocab_files", new_callable=AsyncMock
    ) as mock_get_files:
        mock_get_files.return_value = []
        await fallback_no_state_message(mock_message, mock_session, mock_user)

    mock_message.answer.assert_called_once_with("Сначала настройте бота командой /start")
