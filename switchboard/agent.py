"""Model configuration and LangGraph-backed agent construction."""

from pathlib import Path

from langchain.agents import create_agent
from langchain.agents.middleware import ToolErrorMiddleware
from langchain_deepseek import ChatDeepSeek

from switchboard.tools import TOOLS, InvestigationContext

MODEL = "deepseek-flash"


def create_model():
    return ChatDeepSeek(
        model=MODEL,
        max_tokens=4096,
        timeout=60,
        max_retries=1,
    )


def explain_unavailable_record(error: Exception, request) -> str | None:
    """Handle expected access failures without disclosing record existence."""
    if isinstance(error, PermissionError):
        return (
            "I couldn't retrieve that record. It may not exist, "
            "or you may not have permission to access it."
        )
    return None  # Unexpected failures must still fail the run.


def build_agent(model, now: str):
    """LangChain's agent runs the model/tool loop on LangGraph."""
    return create_agent(
        model=model,
        tools=TOOLS,
        middleware=[ToolErrorMiddleware(on_error=explain_unavailable_record)],
        context_schema=InvestigationContext,
        system_prompt=(Path(__file__).parent / "prompts" / "investigation.md")
        .read_text()
        .format(now=now),
    )
