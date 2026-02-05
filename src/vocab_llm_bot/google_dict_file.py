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
            if col_name.lower() == "status":
                return col_name, col_letter
        return None

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

    def get_random_unlearned_word(self) -> tuple[list[str], int] | None:
        status_col_info = self.get_status_column_info()
        if not status_col_info:
            logger.error("No 'Status' column found in the sheet.")
            return None, None
        _, status_col_letter = status_col_info

        # Get the entire status column
        status_col_range = f"{self.sheet_name}!{status_col_letter}2:{status_col_letter}"
        result = (
            self.sheet.values()
            .get(spreadsheetId=self.google_sheet_id, range=status_col_range)
            .execute()
        )
        status_values = result.get("values", [])

        unlearned_row_indices = []
        for i, row in enumerate(status_values):
            # i + 2 is the actual row number in the sheet
            if not row or (row and row[0].lower() != "learned"):
                unlearned_row_indices.append(i + 2)

        if not unlearned_row_indices:
            return None, None  # All words are learned

        random_row_index = choice(unlearned_row_indices)

        # Now get the data for that row
        row_range = f"{self.sheet_name}!A{random_row_index}:Z{random_row_index}"
        result = (
            self.sheet.values()
            .get(spreadsheetId=self.google_sheet_id, range=row_range)
            .execute()
        )

        word_data = result.get("values", [[]])[0]
        return word_data, random_row_index
