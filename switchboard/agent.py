"""Model configuration and LangGraph-backed agent construction."""

import json
from pathlib import Path

from langchain.agents import create_agent
from langchain.agents.middleware import ToolErrorMiddleware
from langchain_deepseek import ChatDeepSeek

from switchboard.models import InvestigationResult
from switchboard.tools import TOOLS, InvestigationContext

MODEL = "deepseek-flash"


def create_model():
    return ChatDeepSeek(
        model=MODEL,
        extra_body={"thinking": {"type": "enabled"}},
        max_tokens=8192,
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
    """Investigate with thinking and request a final JSON result."""
    prompt = (Path(__file__).parent / "prompts" / "investigation.md").read_text()
    return create_agent(
        model=model,
        tools=TOOLS,
        middleware=[ToolErrorMiddleware(on_error=explain_unavailable_record)],
        context_schema=InvestigationContext,
        system_prompt=prompt.format(
            now=now,
            result_schema=json.dumps(InvestigationResult.model_json_schema()),
        ),
    )
