from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.genai import types

from vocab_llm_bot.google_dict_file import GoogleDictFile
from vocab_llm_bot.training_strategies import (
    Message,
    RoleMessage,
    WordTranslationStrategy,
    WorldPairTrainStrategy,
    get_completion,
)


@pytest.mark.asyncio
async def test_get_completion_basic_success():
    mock_response = MagicMock()
    mock_response.text = "Hello from Gemini"

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    with patch(
        "vocab_llm_bot.training_strategies.get_gemini_client", return_value=mock_client
    ):
        messages = [{"role": RoleMessage.user, "content": "Hi"}]
        result = await get_completion(messages)

        assert result == "Hello from Gemini"
        mock_client.aio.models.generate_content.assert_called_once()
        args, kwargs = mock_client.aio.models.generate_content.call_args
        assert kwargs["model"] == "gemini-3-flash-preview"
        assert len(kwargs["contents"]) == 1
        assert kwargs["contents"][0].role == "user"
        assert kwargs["contents"][0].parts[0].text == "Hi"


@pytest.mark.asyncio
async def test_get_completion_merging_roles():
    mock_response = MagicMock()
    mock_response.text = "OK"

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    with patch(
        "vocab_llm_bot.training_strategies.get_gemini_client", return_value=mock_client
    ):
        messages = [
            {"role": RoleMessage.system, "content": "Instruction 1"},
            {"role": RoleMessage.user, "content": "Question"},
            {"role": RoleMessage.assistant, "content": "Answer"},
            {"role": RoleMessage.assistant, "content": "More info"},
        ]
        await get_completion(messages)

        args, kwargs = mock_client.aio.models.generate_content.call_args
        contents = kwargs["contents"]

        # 4 messages should be merged into 2 contents
        # system (user) + user (user) -> 1 user content with 2 parts
        # assistant (model) + assistant (model) -> 1 model content with 2 parts
        assert len(contents) == 2
        assert contents[0].role == "user"
        assert len(contents[0].parts) == 2
        assert contents[0].parts[0].text == "Instruction 1"
        assert contents[0].parts[1].text == "Question"

        assert contents[1].role == "model"
        assert len(contents[1].parts) == 2
        assert contents[1].parts[0].text == "Answer"
        assert contents[1].parts[1].text == "More info"


@pytest.mark.asyncio
async def test_get_completion_prepend_user():
    mock_response = MagicMock()
    mock_response.text = "OK"

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    with patch(
        "vocab_llm_bot.training_strategies.get_gemini_client", return_value=mock_client
    ):
        # Start with assistant message
        messages = [{"role": RoleMessage.assistant, "content": "Hello"}]
        await get_completion(messages)

        args, kwargs = mock_client.aio.models.generate_content.call_args
        contents = kwargs["contents"]

        # Should have prepended user message
        assert len(contents) == 2
        assert contents[0].role == "user"
        assert contents[0].parts[0].text == "..."
        assert contents[1].role == "model"
        assert contents[1].parts[0].text == "Hello"


@pytest.mark.asyncio
async def test_world_pair_strategy_flow():
    mock_dict = MagicMock(spec=GoogleDictFile)
    strategy = WorldPairTrainStrategy(mock_dict, "English", "Russian")

    with patch(
        "vocab_llm_bot.training_strategies.get_completion",
        AsyncMock(return_value="AI Response"),
    ) as mock_get_completion:
        # 1. next_word
        resp = await strategy.next_word("мир", "world")
        assert resp == "AI Response"
        assert len(strategy._messages_ctx) == 2
        assert strategy._messages_ctx[0]["role"] == RoleMessage.system
        assert "world" in strategy._messages_ctx[0]["content"]
        assert strategy._messages_ctx[1] == {
            "role": RoleMessage.assistant,
            "content": "AI Response",
        }

        # 2. analyze_user_input
        resp2 = await strategy.analyze_user_input("Correct translation")
        assert resp2 == "AI Response"
        assert len(strategy._messages_ctx) == 5
        assert strategy._messages_ctx[2] == {
            "role": RoleMessage.user,
            "content": "Correct translation",
        }
        assert strategy._messages_ctx[3]["role"] == RoleMessage.system
        assert "correct" in strategy._messages_ctx[3]["content"]
