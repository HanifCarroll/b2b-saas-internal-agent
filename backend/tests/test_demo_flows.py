from uuid import UUID

import pytest

from switchboard.demo.cases import list_demo_cases, prepare_demo_case
from switchboard.demo.workspaces import DemoWorkspace, open_demo_workspace


def test_new_visitors_receive_isolated_baseline_workspaces(storage_bridge):
    base = storage_bridge.storage(workspace_id="unused")

    first = open_demo_workspace(workspace_id=None, base_storage=base)
    second = open_demo_workspace(workspace_id=None, base_storage=base)

    assert first.was_created is True
    assert second.was_created is True
    assert first.workspace.id != second.workspace.id
    first.workspace.storage.touch_workspace(updated_at="2026-09-20T00:00:00+00:00")
    second_workspace = second.workspace.storage.get_workspace()
    assert second_workspace is not None
    assert second_workspace["updatedAt"] != "2026-09-20T00:00:00+00:00"


def test_known_workspace_reopens_without_resetting_records(storage_bridge):
    base = storage_bridge.storage(workspace_id="unused")
    created = open_demo_workspace(workspace_id=None, base_storage=base)

    reopened = open_demo_workspace(
        workspace_id=created.workspace.id,
        base_storage=base,
    )

    assert reopened.was_created is False
    assert reopened.workspace.id == created.workspace.id
    assert reopened.workspace.storage.get_ticket(ticket_id="CHG-1042") is not None


def test_prepared_cases_cover_request_approval_and_execution(storage_bridge):
    storage = storage_bridge.storage(workspace_id="case-workspace")
    workspace = DemoWorkspace(
        id=UUID("93f02ff8-20b5-41b3-b176-4da804b3ca6e"), storage=storage
    )

    cases = {item.id: item for item in list_demo_cases()}
    assert set(cases) == {
        "valid-request",
        "unsafe-destination",
        "pending-approval",
        "ready-to-execute",
    }
    for case_id in cases:
        prepared = prepare_demo_case(case_id=case_id, workspace=workspace)
        assert prepared.case_id == case_id
        assert prepared.path.startswith(("/requests/", "/approvals/"))


def test_unknown_case_does_not_replace_workspace(storage):
    before = storage.get_workspace()

    with pytest.raises(ValueError, match="Unknown demo case"):
        prepare_demo_case(
            case_id="missing",
            workspace=DemoWorkspace(
                id=UUID("93f02ff8-20b5-41b3-b176-4da804b3ca6e"), storage=storage
            ),
        )

    assert storage.get_workspace() == before
