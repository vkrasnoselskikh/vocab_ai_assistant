from unittest.mock import MagicMock

from vocab_llm_bot.config import GoogleServiceAccount
from vocab_llm_bot.google_dict_file import GoogleDictFile


class MockGoogleServiceAccount(MagicMock):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("spec", GoogleServiceAccount)
        super().__init__(*args, **kwargs)
        self.get_client_email.return_value = "test@example.com"

    def __repr__(self):
        return f"<Mock spec={GoogleServiceAccount.__name__} id={hex(id(self))}>"


class MockGoogleDictFile(MagicMock):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("spec", GoogleDictFile)
        super().__init__(*args, **kwargs)
        self.get_random_row.return_value = ["hello", "привет"]
        self.get_random_row_excluding.return_value = ["world", "мир"]

    def __repr__(self):
        return f"<Mock spec={GoogleDictFile.__name__} id={hex(id(self))}>"
