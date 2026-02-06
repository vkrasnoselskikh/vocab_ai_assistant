from enum import Enum
from functools import cache
from string import Template
from typing import TypedDict

from google import genai
from google.genai import types

from .config import Config
from .google_dict_file import GoogleDictFile

START_PROMPT = Template("""You are a translation assistant.
Below is the pair - word in $lang_from and translation in $lang_to.

$lang_from: $world_from
$lang_to: $world_to

Rules:
1. Don't greet the user. Start immediately without any introductory phrases.
2. Communicate with the user ONLY in $lang_to.
3. Don't use markdown. Use plain text only.

Task:
Come up with a short sentence using the word "$world_from".
Ask the user to translate this sentence from $lang_to to $lang_from.
""")

WORD_TRANSLATION_PROMPT = Template(
    """You are a translation assistant.

Rules:
1. Don't greet the user. Start immediately without any introductory phrases.
2. Communicate with the user ONLY in $lang_to.
3. Don't use markdown. Use plain text only.

Task:
Ask the user to translate the word "$word_from" from $lang_from to $lang_to.
"""
)

USER_DONT_KNOW_PROMPT = Template(
    "User does not know. Show the correct answer in $lang_to. No greetings. No markdown. Plain text only."
)

ANALYZE_ANSWER_PROMPT = Template(
    'If I answered correctly, write "correct" else "incorrect" and show translation. Answer in $lang_to. No greetings. No markdown. Plain text only.'
)


class RoleMessage(str, Enum):
    system = "system"
    assistant = "assistant"
    user = "user"


class Message(TypedDict):
    role: RoleMessage
    content: str


@cache
def get_gemini_client() -> genai.Client:
    return genai.Client(api_key=Config().gemini_api_key)


async def get_completion(messages: list[Message]) -> str:
    contents: list[types.Content] = []

    for msg in messages:
        # Простое правило: assistant -> model, всё остальное (user/system) -> user
        role = "model" if msg["role"] == RoleMessage.assistant else "user"
        text = msg["content"]

        if contents and contents[-1].role == role:
            # Если роль совпадает с предыдущим сообщением, склеиваем их (Gemini требует чередования)
            if contents[-1].parts is None:
                contents[-1].parts = []
            contents[-1].parts.append(types.Part.from_text(text=text))
        else:
            contents.append(
                types.Content(role=role, parts=[types.Part.from_text(text=text)])
            )

    # Gemini требует, чтобы диалог всегда начинался с 'user'
    if contents and contents[0].role == "model":
        contents.insert(
            0, types.Content(role="user", parts=[types.Part.from_text(text="...")])
        )

    response = await get_gemini_client().aio.models.generate_content(
        model="gemini-3-flash-preview",
        contents=contents,
    )
    return response.text or ""


class WorldPairTrainStrategy:
    def __init__(
        self,
        dict_file: GoogleDictFile,
        lang_from: str,
        lang_to: str,
        lang_from_col: str = "A",
        lang_to_col: str = "B",
    ):
        self.dict_file = dict_file
        # Найти в файле колонки для lang_from и lang_to
        self.lang_from = lang_from
        self.lang_to = lang_to
        self.lang_from_col = lang_from_col
        self.lang_to_col = lang_to_col

        self._messages_ctx: list[Message] = []
        self._current_words: tuple[str, str] | None = None

    async def next_word(self, word_to: str, word_from: str) -> str:
        """Return assistant message"""
        self._messages_ctx = [
            Message(
                role=RoleMessage.system,
                content=START_PROMPT.substitute(
                    lang_from=self.lang_from,
                    lang_to=self.lang_to,
                    world_from=word_from,
                    world_to=word_to,
                ),
            ),
        ]
        assistant = await get_completion(self._messages_ctx)
        self._messages_ctx.append({"role": RoleMessage.assistant, "content": assistant})
        return assistant

    async def analyze_user_input(self, user_input: str) -> str:
        if user_input in ["I dont know", "--"]:
            self._messages_ctx.append(
                {
                    "role": RoleMessage.system,
                    "content": USER_DONT_KNOW_PROMPT.substitute(lang_to=self.lang_to),
                }
            )
            assistant = await get_completion(self._messages_ctx)
            self._messages_ctx.append(
                {"role": RoleMessage.assistant, "content": assistant}
            )
            return assistant

        self._messages_ctx.append({"role": RoleMessage.user, "content": user_input})
        self._messages_ctx.append(
            {
                "role": RoleMessage.system,
                "content": ANALYZE_ANSWER_PROMPT.substitute(lang_to=self.lang_to),
            }
        )

        assistant = await get_completion(self._messages_ctx)
        self._messages_ctx.append({"role": RoleMessage.assistant, "content": assistant})
        return assistant


class WordTranslationStrategy:
    def __init__(
        self,
        dict_file: GoogleDictFile,
        lang_from: str,
        lang_to: str,
        lang_from_col: str = "A",
        lang_to_col: str = "B",
    ):
        self.dict_file = dict_file
        # Найти в файле колонки для lang_from и lang_to
        self.lang_from = lang_from
        self.lang_to = lang_to
        self.lang_from_col = lang_from_col
        self.lang_to_col = lang_to_col

        self._messages_ctx: list[Message] = []
        self._current_words: tuple[str, str] | None = None

    async def next_word(self, word_to: str, word_from: str) -> str:
        """Return assistant message"""
        self._messages_ctx = [
            Message(
                role=RoleMessage.system,
                content=WORD_TRANSLATION_PROMPT.substitute(
                    lang_from=self.lang_from,
                    lang_to=self.lang_to,
                    word_from=word_from,
                ),
            )
        ]
        assistant = await get_completion(self._messages_ctx)
        self._messages_ctx.append(
            Message(role=RoleMessage.assistant, content=assistant)
        )
        return assistant

    async def analyze_user_input(self, user_input: str):
        if user_input in ["I dont know", "--"]:
            self._messages_ctx.append(
                Message(
                    role=RoleMessage.system,
                    content=USER_DONT_KNOW_PROMPT.substitute(lang_to=self.lang_to),
                )
            )
            assistant = await get_completion(self._messages_ctx)
            self._messages_ctx.append(
                Message(role=RoleMessage.assistant, content=assistant)
            )
            return assistant

        self._messages_ctx.append(Message(role=RoleMessage.user, content=user_input))
        self._messages_ctx.append(
            Message(
                role=RoleMessage.system,
                content=ANALYZE_ANSWER_PROMPT.substitute(lang_to=self.lang_to),
            )
        )

        assistant = await get_completion(self._messages_ctx)
        self._messages_ctx.append(
            Message(role=RoleMessage.assistant, content=assistant)
        )
        return assistant
