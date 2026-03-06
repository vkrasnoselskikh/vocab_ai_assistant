# Gemini Telegram Bot: Vocabulary AI Assistant

This Telegram bot helps users learn new languages by connecting to their personal Google Sheet vocabulary file. It uses an LLM to create interactive training sessions and check translations.

## Core Features

### 1. Google Sheet Integration
- The bot connects to a user's Google Sheet, which serves as their personal vocabulary dictionary.
- Access to the Google Sheet is granted via a service account. The user needs to share their Google Sheet with the bot's service account email address.
- It automatically detects the languages being learned by reading the header row of the sheet. For example, if the first row contains "English" and "Russian", the bot understands that these are the languages for training.
- The bot saves the language and its corresponding column index to its database for future reference.
- It assumes the dictionary file always contains two languages: the user's native language and the language they are learning.

### 2. Training Modes
After connecting the Google Sheet, the user can choose between two training modes. 
Both modes operate on an active learning session of 10 words. The bot selects an initial set of 10 words to begin.
- If the user answers correctly, the word is marked as "passed" in the database for the session and is replaced by a new, randomly selected word from the dictionary.
- If the user answers incorrectly or skips the word, it remains in the active 10-word set and will be asked again later.
This ensures the user is always focusing on a small, manageable set of vocabulary at a time.

#### a. Word Translation
- The bot randomly selects a word or phrase from the current 10-word learning session.
- It then prompts the user to provide the translation.

#### b. Sentence Translation
- The bot selects a random word from the current 10-word learning session.
- It uses an LLM to generate a simple sentence containing that word, providing context. This sentence is saved in the bot's database.
- The user is asked to translate the entire sentence.
- The bot uses the LLM to evaluate the user's translation and provides natural-sounding feedback and suggestions if the translation is incorrect or could be improved.
- The process then repeats with a new word from the session.

### 3. LLM-Powered Translation Checking
- After the user submits their translation, the bot uses a Large Language Model (LLM) to verify if the translation is correct. This allows for more flexible and context-aware checking than a simple exact match.

### 4. "I don't know" option
- For every training question, a button with the text "I don't know the translation" is provided. This allows the user to skip a word and see the correct answer without guessing.




# Python Development Rules

## Environment
- Use `uv` for dependency management
- Virtual environment must be in `.venv` directory

## Type Safety
- All functions must have complete type annotations (parameters and return types)
- Prefer `list[str]` over `List[str]` (modern syntax)
- Use `X | None` instead of `Optional[X]`
- No `Any` types unless absolutely necessary (and document why)

## Testing
- Write unit tests for all functions
- Use command `pytest` for testing
- Use command `ruff check` for linting
- Use command `ty check` for type checking
- Test edge cases and error handling

## Documentation
- Write clear and concise docstrings for all functions and classes
- Use type hints in docstrings to describe parameter and return types

Always use context7 for any tasks related to libraries: installation, imports, configuration, updates, integrations, and debugging.

## Project Knowledge (Observed in codebase)

### Runtime and Entry Point
- CLI entry point is `bot = "vocab_llm_bot.bot:main"` in `pyproject.toml`.
- Main bot startup is in `src/vocab_llm_bot/bot.py` with aiogram `Dispatcher`, setup/learning routers, and DB session middleware.
- DB tables are auto-created on startup via `create_all_tables()`.

### Data and Persistence
- Default DB DSN is SQLite async: `sqlite+aiosqlite://<project>/.conf/app.db` (see `DatabaseConfig`).
- Main SQLAlchemy models:
  - `users`
  - `user_vocab_files`
  - `user_vocab_file_columns`
- User language mapping is persisted as two records in `user_vocab_file_columns`.

### Setup Flow (FSM)
- `/start` starts onboarding when no vocab file exists.
- User provides Google Sheet link/id -> bot stores `sheet_id`.
- Bot loads available worksheet tabs and asks user to pick one.
- Bot asks user to select exactly two language columns from header.
- Bot then asks for training mode (`word` or `sentence`) and stores it in `users.training_mode`.

### Training Flow
- `/train` loads up to 10 unlearned words from Google Sheet.
- Learning state is controlled in-memory via cached strategy object.
- If answer is correct, word is removed from active set and row status in Google Sheet is updated to `learned`.
- If answer is wrong or user presses "Я не знаю", word remains in active set.

### Google Sheet Behavior
- `GoogleDictFile` auto-detects/creates `Status` column (case-insensitive check for `"status"`).
- "Learned" detection is based on lowercase text equality with `learned`.
- Header and max rows are memoized with `functools.cache`.

### Caching
- `get_cached_dict_file(...)` and `get_cached_training_strategy(...)` use `aiocache` memory cache with TTL `900` seconds.
- Gemini client is singleton-like via `@cache get_gemini_client()`.

### LLM Layer
- Current generation model: `gemini-3-flash-preview`.
- Message adaptation is implemented to match Gemini alternation requirements (`user`/`model`) in `get_completion`.

### Quality State (Important)
- Run checks with `uv run ...` (`pytest`, `ruff check`, `ty check`), not bare binaries.
- `ruff` has `fix = true`, so `ruff check` can modify files automatically.
- As of current state, tests are partially stale vs implementation:
  - `test_update_word_status` calls old signature with `status_column_letter`.
  - `test_world_pair_strategy_flow` calls outdated `WorldPairTrainStrategy` constructor and old internal attributes.
- As of current state, `ty check` reports type issues in app code and stale tests; do not assume type-check is green before changes.

### Change Discipline for this Repo
- If updating strategy APIs or Google Sheet methods, update tests in `test/` in the same task.
- Preserve current contract: exactly two language columns are expected by training middleware.
- Keep Russian-language user-facing bot messages consistent with existing handlers unless task explicitly requests localization changes.
