import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.mocks import MockGoogleDictFile, MockGoogleServiceAccount
from vocab_llm_bot.handlers.learning import get_words_for_training
from vocab_llm_bot.models import User


@pytest.mark.asyncio
async def test_get_words_for_training(
    dbsession: AsyncSession, orm_user: User, monkeypatch
):
    monkeypatch.setattr(
        "vocab_llm_bot.handlers.setup.GoogleServiceAccount", MockGoogleServiceAccount
    )
    monkeypatch.setattr(
        "vocab_llm_bot.handlers.learning.GoogleDictFile", MockGoogleDictFile
    )

    words = await get_words_for_training(
        dbsession, orm_user.id, MockGoogleDictFile(google_sheet_id="test")
    )
    assert len(words) == 10
