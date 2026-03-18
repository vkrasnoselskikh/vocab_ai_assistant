from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError

from vocab_llm_bot.google_dict_file import GoogleDictFile


@pytest.fixture
def mock_google_dict_file():
    with patch("vocab_llm_bot.google_dict_file.build") as mock_build:
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        
        # Instantiate
        gdf = GoogleDictFile("sheet_id")
        gdf.sheet_name = "Sheet1"
        
        # Mock get_header response
        # A, B, C -> English, Russian, Status
        # We need to mock the response of get_header. 
        # But get_header calls self.sheet.get().execute().
        # It's better to mock get_header directly if we are testing add_word logic mostly, 
        # OR mock the underlying API call which is more robust but verbose.
        
        # Let's mock the underlying API call for get_header
        # This is complex because get_header does heavy parsing.
        # We can mock get_header directly for simplicity in testing add_word logic.
        
        yield gdf, mock_service


def test_add_word_success(mock_google_dict_file):
    gdf, mock_service = mock_google_dict_file
    
    # Mock header: English (A), Russian (B), Status (C)
    # Using side_effect or return_value on the cached method?
    # Since get_header is cached, we might need to patch the method on the class or instance.
    # But patching 'vocab_llm_bot.google_dict_file.GoogleDictFile.get_header' works best.
    
    with patch.object(GoogleDictFile, 'get_header') as mock_get_header, \
         patch.object(GoogleDictFile, 'get_status_column_info') as mock_status_info:
        
        mock_get_header.return_value = [
            ("English", 1, "A"),
            ("Russian", 1, "B"),
            ("Status", 1, "C")
        ]
        mock_status_info.return_value = ("Status", "C")
        
        word_data = {"English": "Cat", "Russian": "Кот"}
        
        gdf.add_word(word_data)
        
        # Verify append call
        # Expected row: ["Cat", "Кот", "unlearned"]
        mock_service.spreadsheets().values().append.assert_called_once()
        call_kwargs = mock_service.spreadsheets().values().append.call_args.kwargs
        
        assert call_kwargs["spreadsheetId"] == "sheet_id"
        assert call_kwargs["range"] == "Sheet1!A1"
        assert call_kwargs["valueInputOption"] == "USER_ENTERED"
        assert call_kwargs["insertDataOption"] == "INSERT_ROWS"
        assert call_kwargs["body"] == {"values": [["Cat", "Кот", "unlearned"]]}


def test_add_word_missing_column(mock_google_dict_file):
    gdf, mock_service = mock_google_dict_file
    
    with patch.object(GoogleDictFile, 'get_header') as mock_get_header, \
         patch.object(GoogleDictFile, 'get_status_column_info') as mock_status_info:
        
        mock_get_header.return_value = [
            ("English", 1, "A"),
            # Russian column missing
            ("Status", 1, "C")
        ]
        mock_status_info.return_value = ("Status", "C")
        
        word_data = {"English": "Cat", "Russian": "Кот"}
        
        gdf.add_word(word_data)
        
        # Expected row: ["Cat", "", "unlearned"] (Russian skipped as column not found, index 1 empty)
        # Wait, if Russian is missing from header, A=English, B=?, C=Status.
        # Header list logic: A=English. C=Status. B is implicitly empty or another column?
        # Our mock header explicitly says C is Status.
        # Code: col_idx = _col_letter_to_index(col_letter) - 1.
        # A=0, C=2. So index 1 is empty.
        
        mock_service.spreadsheets().values().append.assert_called_once()
        body = mock_service.spreadsheets().values().append.call_args.kwargs["body"]
        assert body["values"] == [["Cat", "", "unlearned"]]
