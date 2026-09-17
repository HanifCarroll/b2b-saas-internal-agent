# Project instructions

- Use uv to manage dependencies and run Python tools.
- After changing Python code, run `uv run ruff check --fix .` and `uv run ruff format .`, then review the changes.
- Before finishing, run `uv run ruff check .`, `uv run ruff format --check .`, and `uv run pytest -v`.
- Format long SQL strings manually when needed for readability; Ruff does not format SQL contents.
