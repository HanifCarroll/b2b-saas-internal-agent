"""Validated records and investigation results. Authorization lives elsewhere."""

from typing import Annotated, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
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


class InvestigationResult(Record):
    """Investigator findings, not authorization to save or execute a change."""

    outcome: Literal["proposal_candidate", "blocked"]
    ticket_id: Text | None
    proposed_endpoint: HttpUrl | None
    evidence_ids: list[Text]
    summary: Text
    blockers: list[Text]

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.outcome == "proposal_candidate":
            if self.ticket_id is None:
                raise ValueError("A proposal candidate requires a ticket ID")
            if self.proposed_endpoint is None:
                raise ValueError("A proposal candidate requires a proposed endpoint")
            if not self.evidence_ids:
                raise ValueError("A proposal candidate requires supporting evidence")
            if self.blockers:
                raise ValueError("A proposal candidate cannot have blockers")
        elif not self.blockers:
            raise ValueError("A blocked investigation requires at least one blocker")
        return self
