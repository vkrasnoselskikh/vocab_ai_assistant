import logging
from functools import cache
from random import choice

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from vocab_llm_bot.config import GoogleServiceAccount

logger = logging.getLogger(__name__)
sa = GoogleServiceAccount()


def _col_index_to_letter(index: int) -> str:
    letters = ""
    while index > 0:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _col_letter_to_index(letter: str) -> int:
    index = 0
    for char in letter:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index


class GoogleDictFile:
    def __init__(self, google_sheet_id: str):
        self.google_sheet_id = google_sheet_id
        self.service = build("sheets", "v4", credentials=sa.get_credentials())
        self.sheet = self.service.spreadsheets()
        self._sheet_name: str | None = None
        self._max_rows: int | None = None

    def get_sheets(self):
        try:
            result = self.sheet.get(spreadsheetId=self.google_sheet_id).execute()
            return result.get("sheets", [])
        except HttpError as err:
            logger.error(f"An error occurred: {err}")
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
            fields="sheets(data(rowData(values(effectiveValue))))",
        ).execute()

        rows = result["sheets"][0]["data"][0].get("rowData", [])
        self._max_rows = len(rows)
        return self._max_rows

    @cache
    def get_header(self) -> list[tuple[str, int, str]]:
        try:
            result = self.sheet.get(
                spreadsheetId=self.google_sheet_id,
                ranges=self.sheet_name,
                includeGridData=True,
                fields="sheets(data(startRow,startColumn,rowData(values(effectiveValue,formattedValue))))",
            ).execute()
            data = result.get("sheets", [])[0].get("data", [])[0]
            start_row = data.get("startRow", 0)  # 0-based
            start_col = data.get("startColumn", 0)  # 0-based
            row_data = data.get("rowData", [])
            if not row_data:
                return []
            cells = row_data[0].get("values", [])
            header = []
            for i, cell in enumerate(cells):
                ev = cell.get("effectiveValue") or cell.get("formattedValue") or {}
                if isinstance(ev, dict):
                    val = (
                        ev.get("stringValue")
                        if "stringValue" in ev
                        else ev.get("numberValue", "")
                    )
                else:
                    val = ev
                col_number_1based = start_col + i + 1
                row_number_1based = start_row + 1
                header.append(
                    (val, row_number_1based, _col_index_to_letter(col_number_1based))
                )
            return header
        except HttpError as err:
            logger.error("An error occurred: %s", err)
            return []

    def get_status_column_info(self) -> tuple[str, str] | None:
        header = self.get_header()
        for col_name, _, col_letter in header:
            if str(col_name).lower() == "status":
                return col_name, col_letter
        return None

    def ensure_status_column(self) -> str:
        """Checks for the 'Status' column and creates it if it doesn't exist. Returns the column letter."""
        status_info = self.get_status_column_info()
        if status_info:
            return status_info[1]

        header = self.get_header()
        next_col_index = len(header) + 1
        status_col_letter = _col_index_to_letter(next_col_index)

        try:
            range_to_update = f"{self.sheet_name}!{status_col_letter}1"
            self.sheet.values().update(
                spreadsheetId=self.google_sheet_id,
                range=range_to_update,
                valueInputOption="USER_ENTERED",
                body={"values": [["Status"]]},
            ).execute()
            self.get_header.cache_clear()
            logger.info(f"Created 'Status' column at {status_col_letter}")
            return status_col_letter
        except HttpError as err:
            logger.error(f"Failed to create 'Status' column: {err}")
            raise

    def update_word_status(
        self, row_index: int, status_column_letter: str, status: str
    ):
        try:
            range_to_update = f"{self.sheet_name}!{status_column_letter}{row_index}"
            self.sheet.values().update(
                spreadsheetId=self.google_sheet_id,
                range=range_to_update,
                valueInputOption="USER_ENTERED",
                body={"values": [[status]]},
            ).execute()
        except HttpError as err:
            logger.error(f"An error occurred while updating sheet: {err}")

    def get_random_unlearned_word(
        self, lang_cols: list[str]
    ) -> tuple[list[str] | None, int | None]:
        status_col_letter = self.ensure_status_column()

        # Determine the maximum column we need to fetch
        all_cols = lang_cols + [status_col_letter]
        max_col_index = max(_col_letter_to_index(col) for col in all_cols)
        max_col_letter = _col_index_to_letter(max_col_index)

        # Get all data to filter empty rows and check status
        result = (
            self.sheet.values()
            .get(
                spreadsheetId=self.google_sheet_id,
                range=f"{self.sheet_name}!A2:{max_col_letter}",
            )
            .execute()
        )
        all_values = result.get("values", [])

        status_idx = _col_letter_to_index(status_col_letter) - 1
        lang_indices = [_col_letter_to_index(col) - 1 for col in lang_cols]

        unlearned_rows = []
        for i, row in enumerate(all_values):
            row_num = i + 2
            # Check if status is NOT 'learned'
            status_val = row[status_idx].lower() if len(row) > status_idx else ""
            if status_val == "learned":
                continue

            # Check if both language columns have values
            has_data = True
            for idx in lang_indices:
                if len(row) <= idx or not str(row[idx]).strip():
                    has_data = False
                    break

            if has_data:
                unlearned_rows.append((row, row_num))

        if not unlearned_rows:
            return None, None  # All words are learned or no words found

        return choice(unlearned_rows)
