# Project instructions

- Use uv to manage dependencies and run Python tools.
- Before finishing a turn where you edited Python code, run `uv run ruff check .`, `uv run ruff format --check .`, `uv run pyright`, and `uv run pytest -v`.
- Format long SQL strings manually when needed for readability; Ruff does not format SQL contents.
- All generated code should focus on readability as its highest value. Do not be clever or terse.
