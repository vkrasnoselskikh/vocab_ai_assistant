import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from vocab_llm_bot.handlers.learning import get_words_for_training
from vocab_llm_bot.models import User
from tests.mocks import MockGoogleDictFile, MockGoogleServiceAccount


@pytest.mark.asyncio
async def test_get_words_for_training(
    session: AsyncSession, orm_user: User, monkeypatch
):
    monkeypatch.setattr(
        "vocab_llm_bot.handlers.setup.GoogleServiceAccount", MockGoogleServiceAccount
    )
    monkeypatch.setattr(
        "vocab_llm_bot.handlers.learning.GoogleDictFile", MockGoogleDictFile
    )

    words = await get_words_for_training(
        session, orm_user.id, MockGoogleDictFile(google_sheet_id="test")
    )
    assert len(words) == 10
