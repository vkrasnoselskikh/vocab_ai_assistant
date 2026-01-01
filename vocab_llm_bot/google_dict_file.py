from functools import cache
import logging
from random import choice
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from vocab_llm_bot.config import GoogleServiceAccount

logger = logging.getLogger(__name__)
sa = GoogleServiceAccount()


class GoogleDictFile:
    def __init__(self, google_sheet_id: str):
        self.google_sheet_id = google_sheet_id
        self.service = build('sheets', 'v4', credentials=sa.get_credentials())
        self.sheet = self.service.spreadsheets()
        self._sheet_name: str | None = None
        self._max_rows: int | None = None

    
    def get_sheets(self):
        try:
            result = self.sheet.get(spreadsheetId=self.google_sheet_id).execute()
            return result.get('sheets', [])
        except HttpError as err:
            logger.error(f'An error occurred: {err}')
            return []
        
    
    @property
    def sheet_name(self) -> str | None:
        if self._sheet_name is None:
            raise ValueError("Sheet name is not set")
        return self._sheet_name

    @sheet_name.setter
    def sheet_name(self, sheet_name: str):
        self._sheet_name = sheet_name

    @cache
    def get_max_rows(self) -> int:
        result = self.sheet.get(
            spreadsheetId=self.google_sheet_id,
            ranges=self.sheet_name,
            fields="sheets(data(rowData(values(effectiveValue))))"
        ).execute()

        rows = result['sheets'][0]['data'][0].get('rowData', [])
        self._max_rows = len(rows)
        return self._max_rows

    @cache
    def get_header(self) -> list[str]:
        result = self.sheet.values().get(
            spreadsheetId=self.google_sheet_id,
            range=f'{self.sheet_name}!A1:Z1'
        ).execute()
        header = result.get('values', [[]])[0]
        return header
    

    def get_random_row(self) -> list[str]:
        idx = choice(range(2, self.get_max_rows()))
        result = self.sheet.values().get(
            spreadsheetId=self.google_sheet_id,
            range=f'{self.sheet_name}!A{idx + 2}:z{idx + 2}'
        ).execute()
        return result.get('values', [[]])[0]

