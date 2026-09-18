"""Validated records and investigation results. Authorization lives elsewhere."""

from typing import Annotated, Literal, Self

from langchain_core.messages import AnyMessage
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_serializer,
    model_validator,
)

Text = Annotated[str, Field(min_length=1, pattern=r"\S")]
Role = Literal["support_specialist", "implementation_engineer", "technical_lead"]
Environment = Literal["sandbox", "production"]
ClockTime = Annotated[str, Field(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")]


class Record(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class Employee(Record):
    id: Text
    name: Text
    active: bool
    role: Role
    customer_ids: list[Text]


class Contact(Record):
    id: Text
    name: Text
    email: Text


class ChangeWindow(Record):
    weekday: Literal[
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
    ]
    start: ClockTime
    end: ClockTime
    timezone: Literal["UTC"]  # Current fixtures use UTC windows only.


class Destination(Record):
    environment: Environment
    url: HttpUrl


class Customer(Record):
    id: Text
    name: Text
    authorized_contacts: list[Contact]
    production_change_window: ChangeWindow
    registered_destinations: list[Destination]


class Integration(Record):
    id: Text
    customer_id: Text
    name: Text
    environment: Environment
    endpoint: HttpUrl
    version: Annotated[int, Field(ge=1)]


class Ticket(Record):
    id: Text
    customer_id: Text
    integration_id: Text
    requester_contact_id: Text
    assigned_employee_id: Text
    requested_endpoint: HttpUrl
    created_at: AwareDatetime
    status: Text
    subject: Text
    body: Text


class Proposal(Record):
    """A proposed endpoint change; its existence does not authorize execution."""

    id: Text
    proposed_by_employee_id: Text
    ticket_id: Text
    requester_contact_id: Text
    customer_id: Text
    integration_id: Text
    environment: Environment
    current_endpoint: HttpUrl
    proposed_endpoint: HttpUrl
    expected_configuration_version: Annotated[int, Field(ge=1)]
    created_at: AwareDatetime
    status: Literal["pending_approval"] = "pending_approval"

    @field_serializer("current_endpoint", "proposed_endpoint")
    def serialize_endpoint(self, endpoint: HttpUrl) -> str:
        """Store URLs as strings in graph checkpoints as well as JSON."""
        return str(endpoint)


class Approval(Record):
    """An employee's approval of a saved proposal, not proof of execution."""

    id: Text
    proposal_id: Text
    approved_by_employee_id: Text
    created_at: AwareDatetime


class InvestigationFindings(Record):
    """Readable sections generated with the investigation, not a second model call."""

    overview: Text = Field(description="Brief conclusion and requested change.")
    checks: list[Text] = Field(description="Evidence checks, one finding per item.")
    policy_requirements: list[Text] = Field(
        description="Applicable policy rules, including their conditions and exceptions."
    )
    gaps: list[Text] = Field(description="Unknown or unverified facts; empty if none.")
    recommendation: Text = Field(
        description="What the evidence supports, without claiming a proposal was saved, approved, or executed."
    )


class InvestigationResult(Record):
    """Investigator findings, not authorization to save or execute a change."""

    outcome: Literal["proposal_candidate", "blocked"]
    ticket_id: Text | None
    proposed_endpoint: HttpUrl | None
    evidence_ids: list[Text]
    findings: InvestigationFindings
    blockers: list[Text]

    @field_serializer("proposed_endpoint")
    def serialize_endpoint(self, endpoint: HttpUrl | None) -> str | None:
        return str(endpoint) if endpoint is not None else None

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        # 1. Require complete, consistent fields for a proposal candidate.
        if self.outcome == "proposal_candidate":
            if self.ticket_id is None:
                raise ValueError("A proposal candidate requires a ticket ID")
            if self.proposed_endpoint is None:
                raise ValueError("A proposal candidate requires a proposed endpoint")
            if not self.evidence_ids:
                raise ValueError("A proposal candidate requires supporting evidence")
            if self.blockers:
                raise ValueError("A proposal candidate cannot have blockers")

        # 2. Require an explanation for a blocked investigation.
        elif not self.blockers:
            raise ValueError("A blocked investigation requires at least one blocker")

        return self


class EndpointChangeResult(Record):
    investigation: InvestigationResult
    messages: list[AnyMessage]
    proposal: Proposal | None = None
    was_created: bool | None = None
