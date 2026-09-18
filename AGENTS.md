# Project instructions

- Python code, tests, data, and dependencies live in `backend/`; the Next.js app lives in `frontend/`.
- Run frontend commands from `frontend/`. Use Oxlint (`npm run lint`) and Oxfmt (`npm run format` / `npm run format:check`), not ESLint or Prettier. Verify frontend edits with lint, format check, and `npm run build`.
- Run Python commands from `backend/`. Use uv to manage dependencies and run Python tools.
- Before finishing a turn where you edited Python code, run `uv run ruff check .`, `uv run ruff format --check .`, `uv run pyright`, and `uv run pytest -v`.

## Code readability

- All generated code should focus on readability as its highest value. Do not be clever or terse.
- Prioritize code that is easy to follow for someone learning Python, LangChain, and LangGraph.
- In nontrivial functions with multiple logical stages, use short, numbered comments describing each stage, such as: `# 1. Validate the request against current records.`
- There should always be an empty line before the section comment unless it is the first one.
- Label meaningful stages, not individual statements. Small, obvious functions do not need numbered sections.
- Keep section labels and numbering accurate when changing code.
- Prefer descriptive names and explicit control flow over terse or clever implementations. Comments should clarify intent, not compensate for confusing code.
- Format long SQL strings manually when needed for readability; Ruff does not format SQL contents.
- Separate logical blocks within functions with one blank line, including setup, validation, execution, and output.
- Add a blank line after an early-return block before the next operation, and between validation checks and the work they protect.
- Keep closely related statements together; do not add blank lines between every statement.
- Give each function one clear responsibility. When callers need only part of a function’s behavior, consider extracting that responsibility into a shared function rather than calling the whole function and discarding its result.

- Prefer named fields over positional tuples for business results containing multiple values, including boolean flags. Use a small dataclass for internal results and Pydantic when runtime validation or serialization is needed. Access results by field name; keep ordinary tuples for natural sequences and standard-library conventions.
