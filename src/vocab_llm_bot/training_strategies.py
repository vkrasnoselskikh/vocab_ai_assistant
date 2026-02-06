import random
from enum import Enum
from functools import cache
from string import Template
from typing import TypedDict

from google import genai
from google.genai import types

from .config import Config

WORD_TRAIN_PAIR_PROMPT = Template(
    """You are a translation assistant.

Below is the pair - word in $lang_from and translation in $lang_to.

```csv
$lang_from,$lang_to
$word_from,$word_to
```

Rules:
1. No greetings, no explanations, no instructions.
2. Don't use markdown. Use plain text only.

Task:
Ask the user to translate the word ‘$word_from’ into $lang_to.
"""
)

WORD_TRANSLATE_SENTENCE_PROMPT = Template("""You are a translation game.
Below is the pair - word in $lang_from and translation in $lang_to from user vocabulary.
```csv
$lang_from,$lang_to
$word_from,$word_to
```

Rules:
1. No greetings, no explanations, no instructions.
2. Don't use markdown. Use plain text only.

Task:
Come up with a simple sentence using the word ‘$world_from’.
Write only this sentence in your answer.
""")

ANSWER_IF_DONT_KNOW = Template("✏️ >> $word_to")

USER_DONT_KNOW_PROMPT = Template("I don't know. Translate your sentence to $lang_to")


ANALYZE_ANSWER_PROMPT = Template(
    """\
    Analyze the my answer. If I translate to $lang_to correctly, write "✅ Сorrect"
    else "❌ Incorrect" and show translation.
    Answer in $lang_to.
    """
)


class RoleMessage(str, Enum):
    system = "system"
    assistant = "assistant"
    user = "user"


class Message(TypedDict):
    role: RoleMessage
    content: str


class Word(TypedDict):
    word_from: str
    word_to: str
    row_index: int


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
        words: list[Word],
        lang_from: str,
        lang_to: str,
    ):
        self.words = words
        self.lang_from = lang_from
        self.lang_to = lang_to

        self._messages_ctx: list[Message] = []
        self._current_word: Word | None = None

    async def next_word(self) -> str | None:
        """Return assistant message"""
        if not self.words:
            return None

        self._current_word = random.choice(self.words)
        word_from = self._current_word["word_from"]
        word_to = self._current_word["word_to"]

        self._messages_ctx = [
            Message(
                role=RoleMessage.system,
                content=WORD_TRAIN_PAIR_PROMPT.substitute(
                    lang_from=self.lang_from,
                    lang_to=self.lang_to,
                    word_from=word_from,
                    word_to=word_to,
                ),
            ),
        ]
        assistant = f"Переведи слово '{word_from}'"
        self._messages_ctx.append({"role": RoleMessage.assistant, "content": assistant})
        return assistant

    async def analyze_user_input(self, user_input: str) -> tuple[str, bool]:
        if self._current_word is None:
            return "Ошибка: текущее слово не определено", False

        if user_input in ["I dont know", "--"]:
            assistant = ANSWER_IF_DONT_KNOW.substitute(
                word_to=self._current_word["word_to"]
            )
            self._messages_ctx.append(
                {"role": RoleMessage.assistant, "content": assistant}
            )
            return assistant, False

        self._messages_ctx.append({"role": RoleMessage.user, "content": user_input})
        self._messages_ctx.append(
            {
                "role": RoleMessage.system,
                "content": ANALYZE_ANSWER_PROMPT.substitute(lang_to=self.lang_to),
            }
        )

        assistant = await get_completion(self._messages_ctx)
        self._messages_ctx.append({"role": RoleMessage.assistant, "content": assistant})

        is_correct = "✅" in assistant

        if is_correct and self._current_word in self.words:
            self.words.remove(self._current_word)

        return assistant, is_correct


class WordTranslationSentenceStrategy:
    def __init__(
        self,
        words: list[Word],
        lang_from: str,
        lang_to: str,
    ):
        self.words = words
        self.lang_from = lang_from
        self.lang_to = lang_to

        self._messages_ctx: list[Message] = []
        self._current_word: Word | None = None

    async def next_word(self) -> str | None:
        """Return assistant message"""
        if not self.words:
            return None

        self._current_word = random.choice(self.words)

        self._messages_ctx = [
            Message(
                role=RoleMessage.system,
                content=WORD_TRAIN_PAIR_PROMPT.substitute(
                    lang_from=self.lang_from,
                    lang_to=self.lang_to,
                    word_from=self._current_word["word_from"],
                    word_to=self._current_word["word_to"],
                ),
            )
        ]
        assistant = await get_completion(self._messages_ctx)
        self._messages_ctx.append(
            Message(role=RoleMessage.assistant, content=assistant)
        )
        return assistant

    async def analyze_user_input(self, user_input: str) -> tuple[str, bool]:
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
            return assistant, False

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

        is_correct = "✅" in assistant

        if is_correct and self._current_word in self.words:
            self.words.remove(self._current_word)

        return assistant, is_correct
