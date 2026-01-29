class MockGoogleServiceAccount:
    def get_client_email(self):
        return "test@example.com"


class MockGoogleDictFile:
    def __init__(self, google_sheet_id: str):
        pass

    def get_random_row(self):
        return ["hello", "привет"]

    def get_random_row_excluding(self, exclude: list[str]):
        return ["world", "мир"]
