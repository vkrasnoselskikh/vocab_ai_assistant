import logging
import random
from abc import ABC, abstractmethod
from enum import Enum
from functools import cache
from string import Template
from typing import TypedDict

from attr import s
from google import genai
from google.genai import types
from pandas.tests.indexing.multiindex.test_indexing_slow import n

from .config import Config

logger = logging.getLogger(__name__)

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
Come up with a simple sentence using the word ‘$word_from’.
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


class TrainStrategy(ABC):
    def __init__(
        self,
        lang_from: str,
        lang_to: str,
    ):
        self.words = []
        self.lang_from = lang_from
        self.lang_to = lang_to

        self.messages_ctx: list[Message] = []
        self.current_word: Word | None = None
        logger.info(
            f"init {self.__class__.__name__} with {self.lang_from} -> {self.lang_to}"
        )

    def set_words(self, words: list[Word]):
        self.words = words
        logger.info(f"set {self.__class__.__name__} with {len(words)} words")

    def choice_word(self) -> Word:
        if not len(self.words):
            raise ValueError("No words")
        self.current_word = random.choice(self.words)
        logger.info(f"choise {self.__class__.__name__}  {self.current_word=}")
        return self.current_word

    def get_current_word(self) -> Word:
        if self.current_word is None:
            raise ValueError("No current word")
        return self.current_word

    @abstractmethod
    async def next_word(self) -> str | None: ...

    @abstractmethod
    async def analyze_user_input(self, user_input: str) -> tuple[str, bool]: ...


class WorldPairTrainStrategy(TrainStrategy):
    async def next_word(self) -> str | None:
        """Return assistant message"""
        try:
            res = self.choice_word()
        except ValueError:
            return None
        word_from = res["word_from"]
        word_to = res["word_to"]

        self.messages_ctx = [
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
        self.messages_ctx.append({"role": RoleMessage.assistant, "content": assistant})
        return assistant

    async def analyze_user_input(self, user_input: str) -> tuple[str, bool]:
        try:
            current_word = self.get_current_word()
        except ValueError as e:
            return f"Ошибка: {str(e)}", False

        if user_input in ["I dont know", "--"]:
            assistant = ANSWER_IF_DONT_KNOW.substitute(word_to=current_word["word_to"])
            self.messages_ctx.append(
                {"role": RoleMessage.assistant, "content": assistant}
            )
            return assistant, False

        self.messages_ctx.append({"role": RoleMessage.user, "content": user_input})
        self.messages_ctx.append(
            {
                "role": RoleMessage.system,
                "content": ANALYZE_ANSWER_PROMPT.substitute(lang_to=self.lang_to),
            }
        )

        assistant = await get_completion(self.messages_ctx)
        self.messages_ctx.append({"role": RoleMessage.assistant, "content": assistant})

        is_correct = "✅" in assistant

        if is_correct:
            self.words.remove(current_word)

        return assistant, is_correct


class WordTranslationSentenceStrategy(TrainStrategy):
    async def next_word(self) -> str | None:
        """Return assistant message"""
        try:
            res = self.choice_word()
        except ValueError:
            return None

        self.messages_ctx = [
            Message(
                role=RoleMessage.system,
                content=WORD_TRANSLATE_SENTENCE_PROMPT.substitute(
                    lang_from=self.lang_from,
                    lang_to=self.lang_to,
                    word_from=res["word_from"],
                    word_to=res["word_to"],
                ),
            )
        ]
        assistant = await get_completion(self.messages_ctx)
        self.messages_ctx.append(Message(role=RoleMessage.assistant, content=assistant))
        return assistant

    async def analyze_user_input(self, user_input: str) -> tuple[str, bool]:
        if user_input in ["I dont know", "--"]:
            self.messages_ctx.append(
                Message(
                    role=RoleMessage.system,
                    content=USER_DONT_KNOW_PROMPT.substitute(lang_to=self.lang_to),
                )
            )
            assistant = await get_completion(self.messages_ctx)
            self.messages_ctx.append(
                Message(role=RoleMessage.assistant, content=assistant)
            )
            return assistant, False

        self.messages_ctx.append(Message(role=RoleMessage.user, content=user_input))
        self.messages_ctx.append(
            Message(
                role=RoleMessage.system,
                content=ANALYZE_ANSWER_PROMPT.substitute(lang_to=self.lang_to),
            )
        )

        assistant = await get_completion(self.messages_ctx)
        self.messages_ctx.append(Message(role=RoleMessage.assistant, content=assistant))

        is_correct = "✅" in assistant

        if is_correct and self.current_word in self.words:
            self.words.remove(self.current_word)

        return assistant, is_correct
