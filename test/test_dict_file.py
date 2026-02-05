from unittest.mock import MagicMock, patch

import pytest

from vocab_llm_bot.google_dict_file import GoogleDictFile


@pytest.fixture
def mocked_google_dict_file():
    """This fixture provides a GoogleDictFile instance where the Google API is mocked."""
    with (
        patch("vocab_llm_bot.google_dict_file.sa") as mock_sa,
        patch("vocab_llm_bot.google_dict_file.build") as mock_build,
    ):
        # Mock the credentials
        mock_sa.get_credentials.return_value = MagicMock()

        # Mock the service returned by build()
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        # --- Configure the mock service for various calls ---

        # For get_header
        header_result = {
            "sheets": [
                {
                    "data": [
                        {
                            "startRow": 0,
                            "startColumn": 0,
                            "rowData": [
                                {
                                    "values": [
                                        {"effectiveValue": {"stringValue": "English"}},
                                        {"effectiveValue": {"stringValue": "Russian"}},
                                        {"effectiveValue": {"stringValue": "Status"}},
                                    ]
                                }
                            ],
                        }
                    ]
                }
            ]
        }

        # For get_max_rows
        max_rows_result = {"sheets": [{"data": [{"rowData": [{}, {}, {}, {}, {}]}]}]}

        # For get_random_unlearned_word (status column)
        status_column_result = {"values": [["learned"], [], ["learned"], [""]]}

        # For get_random_unlearned_word (row data)
        row_data_result = {"values": [["world", "мир", ""]]}

        # Configure the 'get' method of spreadsheets()
        mock_get_method = MagicMock()

        # This is the tricky part: side_effect to return different mocks for different calls to `get`
        def get_side_effect(*args, **kwargs):
            if kwargs.get("includeGridData"):
                return MagicMock(execute=MagicMock(return_value=header_result))
            else:
                return MagicMock(execute=MagicMock(return_value=max_rows_result))

        mock_get_method.side_effect = get_side_effect
        mock_service.spreadsheets.return_value.get = mock_get_method

        # Configure the 'get' method of spreadsheets().values()
        mock_values_get_method = MagicMock()

        def values_get_side_effect(*args, **kwargs):
            range_str = kwargs.get("range", "")
            if "C" in range_str:  # A simple way to distinguish the status column call
                return MagicMock(execute=MagicMock(return_value=status_column_result))
            return MagicMock(execute=MagicMock(return_value=row_data_result))

        mock_values_get_method.side_effect = values_get_side_effect
        mock_service.spreadsheets.return_value.values.return_value.get = (
            mock_values_get_method
        )

        # Create the instance to be tested
        dict_file = GoogleDictFile(google_sheet_id="fake_id")
        dict_file.sheet_name = "English"

        # Clear caches before returning to ensure mocks are used
        dict_file.get_header.cache_clear()
        dict_file.get_max_rows.cache_clear()

        yield dict_file


def test_get_max_rows(mocked_google_dict_file: GoogleDictFile):
    max_rows = mocked_google_dict_file.get_max_rows()
    assert max_rows == 5


def test_get_header(mocked_google_dict_file: GoogleDictFile):
    header = mocked_google_dict_file.get_header()
    assert header[0] == ("English", 1, "A")
    assert header[1] == ("Russian", 1, "B")
    assert header[2] == ("Status", 1, "C")


def test_get_status_column_info(mocked_google_dict_file: GoogleDictFile):
    info = mocked_google_dict_file.get_status_column_info()
    assert info == ("Status", "C")


def test_get_random_unlearned_word(mocked_google_dict_file: GoogleDictFile):
    word_data, row_index = mocked_google_dict_file.get_random_unlearned_word()
    assert word_data == ["world", "мир", ""]
    assert row_index in [2, 4, 5]  # unlearned rows are 2 and 4, 5 is empty


def test_update_word_status(mocked_google_dict_file: GoogleDictFile):
    mocked_google_dict_file.update_word_status(
        row_index=3, status_column_letter="C", status="learned"
    )
    update_mock = mocked_google_dict_file.sheet.values().update
    update_mock.assert_called_once_with(
        spreadsheetId="fake_id",
        range="English!C3",
        valueInputOption="USER_ENTERED",
        body={"values": [["learned"]]},
    )
