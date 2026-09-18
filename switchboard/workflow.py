import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NotRequired, TypedDict

from langchain.agents import AgentState
from langchain.agents.middleware import InputAgentState, OutputAgentState
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from langgraph.types import interrupt

from switchboard.integrations.change_management import get_proposal, save_proposal
from switchboard.models import EndpointChangeResult, InvestigationResult, Proposal
from switchboard.proposals import validate_proposal
from switchboard.tools import InvestigationContext, employee_session


# Dependencies supplied by the application that the workflow will use
@dataclass(frozen=True)
class EndpointChangeContext:
    agent: (
        CompiledStateGraph[
            AgentState[Any],
            InvestigationContext | None,
            InputAgentState,
            OutputAgentState[Any],
        ]
        | None
    )
    investigation_context: InvestigationContext
    proposals_database_path: Path
    reviewer_employee_id: str | None = None


class EndpointChangeWorkflowState(TypedDict):
    request: str
    investigation: NotRequired[InvestigationResult]
    proposal: NotRequired[Proposal]
    was_created: NotRequired[bool]
    messages: NotRequired[list[BaseMessage]]
    reviewed_by_employee_id: NotRequired[str]


def investigate_request(
    state: EndpointChangeWorkflowState, runtime: Runtime[EndpointChangeContext]
):
    # 1. Require the investigator and capture the initial business records.
    agent = runtime.context.agent
    if agent is None:
        raise ValueError("Starting an investigation requires an agent")
    employee_context = runtime.context.investigation_context
    with closing(sqlite3.connect(employee_context.database_path)) as connection:
        database_before = list(connection.iterdump())

    # 2. Run the agent and verify read-only behavior even if it fails.
    try:
        result = agent.invoke(
            {"messages": [HumanMessage(content=state["request"])]},
            context=employee_context,
            config={"recursion_limit": 12},
        )
    finally:
        # Check even when the agent fails, before any proposal can be prepared.
        with closing(sqlite3.connect(employee_context.database_path)) as connection:
            database_after = list(connection.iterdump())
        if database_after != database_before:
            raise RuntimeError("Investigation changed business records")

    # 3. Validate the answer and return the investigation with its messages.
    investigation = InvestigationResult.model_validate_json(result["messages"][-1].text)

    return {"investigation": investigation, "messages": result["messages"]}


def prepare_proposal(
    state: EndpointChangeWorkflowState, runtime: Runtime[EndpointChangeContext]
):
    # 1. Require a completed investigation.
    investigation = state.get("investigation")
    if investigation is None:
        raise ValueError("Cannot prepare a proposal without an investigation")

    # 2. Validate and save using the trusted employee session.
    with employee_session(runtime.context.investigation_context) as session:
        proposal = validate_proposal(investigation=investigation, session=session)
        proposal, was_created = save_proposal(
            proposal=proposal,
            session=session,
            database_path=runtime.context.proposals_database_path,
        )

    # 3. Return the saved proposal and whether it was created.
    return {"proposal": proposal, "was_created": was_created}


def review_proposal(
    state: EndpointChangeWorkflowState, runtime: Runtime[EndpointChangeContext]
):
    """Pause for a read acknowledgment; this never approves a change."""
    # 1. Require a saved proposal and pause for external review.
    proposal = state.get("proposal")
    if proposal is None:
        raise ValueError("Cannot review without a proposal")
    response = interrupt(
        {
            "proposal_id": proposal.id,
            "message": "Review the saved proposal, then acknowledge review. This is not approval.",
        }
    )
    # 2. Validate the acknowledgment and require a reviewer identity.
    if response != {"action": "acknowledge_review"}:
        raise ValueError("Expected a review acknowledgment, not an approval decision")
    reviewer_id = runtime.context.reviewer_employee_id
    if reviewer_id is None:
        raise PermissionError("A reviewer session is required")
    # 3. Recheck reviewer access and confirm the proposal is unchanged.
    reviewer_context = InvestigationContext(
        database_path=runtime.context.investigation_context.database_path,
        employee_id=reviewer_id,
    )
    with employee_session(reviewer_context) as session:
        stored = get_proposal(
            session=session,
            proposal_id=proposal.id,
            database_path=runtime.context.proposals_database_path,
        )
    if stored != proposal:
        raise ValueError("Proposal changed since review was requested")
    # 4. Record acknowledgment only; approval status stays unchanged.
    return {"reviewed_by_employee_id": reviewer_id}


def route_after_investigation(state: EndpointChangeWorkflowState):
    # 1. Require the result produced by the investigation node.
    investigation = state.get("investigation")

    if investigation is None:
        raise ValueError("Cannot route without an investigation result")

    # 2. Return the outcome used by the conditional edge.
    return investigation.outcome


# Create the graph
workflow = StateGraph(
    EndpointChangeWorkflowState,
    context_schema=EndpointChangeContext,
    output_schema=EndpointChangeResult,
)

# Add nodes
workflow.add_node("investigate_request", investigate_request)
workflow.add_node("prepare_proposal", prepare_proposal)
workflow.add_node("review_proposal", review_proposal)

# Add edges
workflow.add_edge(START, "investigate_request")
workflow.add_conditional_edges(
    "investigate_request",
    route_after_investigation,
    path_map={
        "proposal_candidate": "prepare_proposal",
        "blocked": END,
    },
)
workflow.add_edge("prepare_proposal", "review_proposal")
workflow.add_edge("review_proposal", END)
endpoint_change_graph = workflow.compile()
