"""Result consistency checks do not establish business authorization."""

import json

import pytest
from pydantic import ValidationError

from switchboard.models import InvestigationResult


@pytest.fixture
def candidate():
    return {
        "outcome": "proposal_candidate",
        "ticket_id": "CHG-1042",
        "proposed_endpoint": "https://events.acme.example/deals",
        "evidence_ids": ["CHG-1042", "acme", "int-acme-prod", "endpoint-change-v2"],
        "summary": "The request supports preparing a proposal; approval is unverified.",
        "blockers": [],
    }


def test_valid_candidate(candidate):
    result = InvestigationResult.model_validate_json(json.dumps(candidate))
    assert result.ticket_id == "CHG-1042"
    assert result.outcome == "proposal_candidate"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("ticket_id", None, "requires a ticket ID"),
        ("proposed_endpoint", None, "requires a proposed endpoint"),
        ("evidence_ids", [], "requires supporting evidence"),
        ("blockers", ["Unregistered destination"], "cannot have blockers"),
    ],
)
def test_candidate_rejects_inconsistent_fields(candidate, field, value, message):
    candidate[field] = value
    with pytest.raises(ValidationError, match=message):
        InvestigationResult.model_validate_json(json.dumps(candidate))


def test_blocked_result_can_have_no_ticket_or_endpoint():
    # 1. Set up inputs and exercise the behavior under test.
    result = InvestigationResult(
        outcome="blocked",
        ticket_id=None,
        proposed_endpoint=None,
        evidence_ids=[],
        summary="The requested record is unavailable.",
        blockers=["Required evidence could not be retrieved."],
    )
    # 2. Verify the expected result and any safety guarantees.
    assert result.ticket_id is None


def test_blocked_result_requires_a_reason(candidate):
    candidate["outcome"] = "blocked"
    with pytest.raises(ValidationError, match="requires at least one blocker"):
        InvestigationResult.model_validate_json(json.dumps(candidate))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ticket_id", " "),
        ("proposed_endpoint", "not-a-url"),
        ("summary", " "),
        ("evidence_ids", [" "]),
        ("outcome", "approved"),
    ],
)
def test_invalid_field_values_are_rejected(candidate, field, value):
    candidate[field] = value
    with pytest.raises(ValidationError):
        InvestigationResult.model_validate_json(json.dumps(candidate))
