"""Capture and read the exact records used by an investigation."""

import json
from datetime import datetime
from uuid import UUID

from langchain_core.messages import BaseMessage, ToolMessage
from pydantic import ValidationError

from switchboard.integrations import (
    configuration_service,
    customer_registry,
    policy_library,
    support_desk,
)
from switchboard.investigation.runs import load_run, require_run_access
from switchboard.investigation.tools import InvestigationContext, employee_session
from switchboard.models import (
    Customer,
    EndpointChangeResult,
    EvidenceDocument,
    EvidenceKind,
    EvidenceSnapshot,
    Integration,
    InvestigationEvidenceDetail,
    PolicyDocument,
    Ticket,
)
from switchboard.storage import WorkspaceStorage


def capture_investigation_evidence(
    *, messages: list[BaseMessage], captured_at: datetime
) -> list[EvidenceSnapshot]:
    """Convert successful domain tool results into immutable evidence snapshots."""
    evidence: list[EvidenceSnapshot] = []

    for message in messages:
        if not isinstance(message, ToolMessage) or not isinstance(message.content, str):
            continue

        try:
            content = json.loads(message.content)
            if message.name == "get_ticket":
                evidence.append(
                    _snapshot(
                        kind="ticket",
                        document=Ticket.model_validate_json(message.content),
                        captured_at=captured_at,
                    )
                )
            elif message.name == "get_customer":
                evidence.append(
                    _snapshot(
                        kind="customer",
                        document=Customer.model_validate_json(message.content),
                        captured_at=captured_at,
                    )
                )
            elif message.name == "get_integration":
                evidence.append(
                    _snapshot(
                        kind="integration",
                        document=Integration.model_validate_json(message.content),
                        captured_at=captured_at,
                    )
                )
            elif message.name == "list_policies":
                evidence.extend(
                    _snapshot(
                        kind="policy",
                        document=PolicyDocument.model_validate(item),
                        captured_at=captured_at,
                    )
                    for item in content
                )
        except (json.JSONDecodeError, TypeError, ValidationError):
            continue

    return evidence


def _snapshot(*, kind, document, captured_at: datetime) -> EvidenceSnapshot:
    return EvidenceSnapshot(
        id=document.id,
        kind=kind,
        captured_at=captured_at,
        document=document,
    )


def read_investigation_evidence(
    *,
    run_id: UUID,
    evidence_id: str,
    employee_id: str,
    storage: WorkspaceStorage,
) -> InvestigationEvidenceDetail:
    """Return one authorized snapshot and its current record when still accessible."""
    context = InvestigationContext(storage=storage, employee_id=employee_id)
    run = load_run(storage=storage, run_id=run_id)
    require_run_access(context=context, run=run)
    result = EndpointChangeResult.model_validate_json(json.dumps(run["result"]))
    snapshot = next(
        (item for item in result.evidence if item.id == evidence_id),
        None,
    )
    if snapshot is None:
        raise FileNotFoundError("Evidence unavailable")

    try:
        current_document = _read_current_document(
            context=context,
            kind=snapshot.kind,
            evidence_id=evidence_id,
        )
    except PermissionError:
        current_document = None

    return InvestigationEvidenceDetail(
        snapshot=snapshot,
        current_document=current_document,
        has_changed=(
            None if current_document is None else current_document != snapshot.document
        ),
    )


def _read_current_document(
    *, context: InvestigationContext, kind: EvidenceKind, evidence_id: str
) -> EvidenceDocument | None:
    with employee_session(context) as session:
        if kind == "ticket":
            return support_desk.get_ticket(session=session, ticket_id=evidence_id)
        if kind == "customer":
            return customer_registry.get_customer(
                session=session,
                customer_id=evidence_id,
            )
        if kind == "integration":
            return configuration_service.get_integration(
                session=session,
                integration_id=evidence_id,
            )

        return next(
            (
                PolicyDocument.model_validate(policy)
                for policy in policy_library.list_policies(session)
                if policy["id"] == evidence_id
            ),
            None,
        )
