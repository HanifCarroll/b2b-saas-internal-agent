from dataclasses import dataclass
from typing import Any, NotRequired, TypedDict

from langchain.agents import AgentState
from langchain.agents.middleware import InputAgentState, OutputAgentState
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime

from switchboard.integrations.change_management import save_proposal
from switchboard.models import EndpointChangeResult, InvestigationResult, Proposal
from switchboard.proposals import validate_proposal
from switchboard.tools import InvestigationContext, employee_session


# Dependencies supplied by the application that the workflow will use
@dataclass(frozen=True)
class EndpointChangeContext:
    agent: CompiledStateGraph[
        AgentState[Any],
        InvestigationContext | None,
        InputAgentState,
        OutputAgentState[Any],
    ]
    investigation_context: InvestigationContext


class EndpointChangeWorkflowState(TypedDict):
    request: str
    investigation: NotRequired[InvestigationResult]
    proposal: NotRequired[Proposal]
    was_created: NotRequired[bool]
    messages: NotRequired[list[BaseMessage]]


def investigate_request(
    state: EndpointChangeWorkflowState, runtime: Runtime[EndpointChangeContext]
):
    # 1. Run the investigator; its tools enforce read-only database connections.
    result = runtime.context.agent.invoke(
        {"messages": [HumanMessage(content=state["request"])]},
        context=runtime.context.investigation_context,
        config={"recursion_limit": 12},
    )

    # 2. Validate the answer and return the investigation with its messages.
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
            database_path=runtime.context.investigation_context.database_path,
        )

    # 3. Return the saved proposal and whether it was created.
    return {"proposal": proposal, "was_created": was_created}


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
workflow.add_edge("prepare_proposal", END)
endpoint_change_graph = workflow.compile()
