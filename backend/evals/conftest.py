"""Load local evaluation credentials before the LangSmith pytest plugin runs."""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)
