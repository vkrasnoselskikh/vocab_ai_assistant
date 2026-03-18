from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.genai import types

from vocab_llm_bot.llm import RoleMessage, get_completion


@pytest.mark.asyncio
async def test_get_completion():
    # Mock the Client and its response
    with patch("vocab_llm_bot.llm.get_gemini_client") as mock_get_client:
        mock_client_instance = MagicMock()
        mock_get_client.return_value = mock_client_instance
        
        mock_response = MagicMock()
        mock_response.text = "Hello, world!"
        
        # Async mock for generate_content
        mock_generate = AsyncMock(return_value=mock_response)
        mock_client_instance.aio.models.generate_content = mock_generate

        messages = [
            {"role": RoleMessage.user, "content": "Hi"},
            {"role": RoleMessage.assistant, "content": "Hello"},
            {"role": RoleMessage.user, "content": "How are you?"}
        ]
        
        response = await get_completion(messages)
        
        assert response == "Hello, world!"
        
        # Verify call arguments
        mock_generate.assert_called_once()
        call_args = mock_generate.call_args
        assert call_args.kwargs["model"] == "gemini-3-flash-preview"
        contents = call_args.kwargs["contents"]
        
        # Check that roles are correctly mapped and alternating
        # user -> user
        # assistant -> model
        # user -> user
        assert len(contents) == 3
        assert contents[0].role == "user"
        assert contents[0].parts[0].text == "Hi"
        assert contents[1].role == "model"
        assert contents[1].parts[0].text == "Hello"
        assert contents[2].role == "user"
        assert contents[2].parts[0].text == "How are you?"
