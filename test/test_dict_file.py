import pytest
from vocab_llm_bot.google_dict_file import GoogleDictFile 


@pytest.fixture
def dict_file() -> GoogleDictFile:
    google_sheet_id = "1I6vXrDOB5AXqwPltLW5RNTrvMg2dJ8sdPmiCuNr4C7I"
    f = GoogleDictFile(google_sheet_id=google_sheet_id)
    f.sheet_name = "English"
    return f


def test_get_max_rows(dict_file: GoogleDictFile):
    max_rows = dict_file.get_max_rows()
    assert isinstance(max_rows, int)
    assert max_rows > 0


def test_get_header(dict_file: GoogleDictFile):
    header = dict_file.get_header()
    assert header[0] == ('English', 1, 'A')
    assert header[1] == ('Russian', 1, 'B')

def test_get_random_row(dict_file: GoogleDictFile):
    row = dict_file.get_random_row()
    assert isinstance(row, list)