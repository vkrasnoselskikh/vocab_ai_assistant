import logging
from random import choice
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from vocab_llm_bot.config import GoogleServiceAccount

logger = logging.getLogger(__name__)
sa = GoogleServiceAccount()


class DictFile:
    def __init__(self, google_sheet_id: str):
        self.google_sheet_id = google_sheet_id
        self.service = build('sheets', 'v4', credentials=sa.get_credentials())
        self.sheet = self.service.spreadsheets()

        self._vocab_sheet_name: str | None = None

    
    def get_sheets(self):
        try:
            result = self.sheet.get(spreadsheetId=self.google_sheet_id).execute()
            return result.get('sheets', [])
        except HttpError as err:
            logger.error(f'An error occurred: {err}')
            return []
        
    
    @property
    def vocab_sheet_name(self) -> str:
        return self._vocab_sheet_name or 'Vocabulary'

    @vocab_sheet_name.setter
    def vocab_sheet_name(self, sheet_name: str):
        self._vocab_sheet_name = sheet_name


    def max_rows(self) -> int:
        result = self.sheet.get(
            spreadsheetId=self.google_sheet_id,
            ranges=self.vocab_sheet_name,
            fields="sheets(data(rowData(values(effectiveValue))))"
        ).execute()

        rows = result['sheets'][0]['data'][0].get('rowData', [])
        return len(rows)
       

    
    def get_language_params(self) -> tuple[str, str]:
        return 'English', 'Russian' # Todo  - get language params from file

    def get_random_word(self) -> tuple[str, str]:
        idx = choice(100)
        return f'English_word_{idx}', f'Russian_word_{idx}'
        # eng_word = self.df.iloc[idx]['English']
        # rus_word = self.df.iloc[idx]['Russian']
        # return eng_word, rus_word
