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
