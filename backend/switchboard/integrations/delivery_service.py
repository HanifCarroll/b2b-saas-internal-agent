"""Deterministic synthetic delivery used by the hosted demonstration."""

from dataclasses import dataclass

from switchboard.models import DeliveryOutcome


@dataclass(frozen=True)
class DeliveryTestResult:
    outcome: DeliveryOutcome
    test_event_id: str
    evidence: str


def send_synthetic_test_event(
    *, destination: str, test_event_id: str
) -> DeliveryTestResult:
    """Return deterministic evidence for the demo's controlled receiver."""
    return DeliveryTestResult(
        outcome="delivered",
        test_event_id=test_event_id,
        evidence=f"Synthetic event {test_event_id} was accepted by {destination}.",
    )
