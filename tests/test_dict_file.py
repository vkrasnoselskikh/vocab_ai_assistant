import pytest
from vocab_llm_bot.dict_file import DictFile


@pytest.fixture
def dict_file() -> DictFile:
    google_sheet_id = "1I6vXrDOB5AXqwPltLW5RNTrvMg2dJ8sdPmiCuNr4C7I"
    f = DictFile(google_sheet_id=google_sheet_id)
    f.vocab_sheet_name = "English"
    return f


def test_get_max_rows(dict_file: DictFile):
    max_rows = dict_file.max_rows()
    assert isinstance(max_rows, int)
    assert max_rows > 0


def test_get_language_params(dict_file: DictFile):
    lang_from, lang_to = dict_file.get_language_params()
    assert lang_from == 'English'
    assert lang_to == 'Russian'

def test_get_random_word(dict_file: DictFile):
    word_from, word_to = dict_file.get_random_word()
    assert isinstance(word_from, str)
    assert isinstance(word_to, str)
    assert len(word_from) > 0
    assert len(word_to) > 0