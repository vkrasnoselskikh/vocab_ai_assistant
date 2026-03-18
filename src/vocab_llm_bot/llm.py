import logging
from enum import Enum
from functools import cache
from typing import TypedDict

from google import genai
from google.genai import types

from .config import Config

logger = logging.getLogger(__name__)


@cache
def get_gemini_client() -> genai.Client:
    return genai.Client(api_key=Config().gemini_api_key)


class RoleMessage(str, Enum):
    system = "system"
    assistant = "assistant"
    user = "user"


class Message(TypedDict):
    role: RoleMessage
    content: str


async def get_completion(messages: list[Message], model: str = "gemini-3-flash-preview") -> str:
    contents: list[types.Content] = []

    for msg in messages:
        # Simple rule: assistant -> model, everything else (user/system) -> user
        role = "model" if msg.get("role") == RoleMessage.assistant else "user"
        text = msg.get("content", "")

        if contents and contents[-1].role == role:
            if contents[-1].parts is None:
                contents[-1].parts = []
            contents[-1].parts.append(types.Part.from_text(text=text))
        else:
            contents.append(
                types.Content(role=role, parts=[types.Part.from_text(text=text)])
            )

    # Gemini requires dialog to always start with 'user'
    if contents and contents[0].role == "model":
        contents.insert(
            0, types.Content(role="user", parts=[types.Part.from_text(text="...")])
        )

    client = get_gemini_client()
    response = await client.aio.models.generate_content(
        model=model,
        contents=contents,
    )
    return response.text or ""
