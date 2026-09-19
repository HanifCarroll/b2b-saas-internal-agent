from datetime import datetime, timezone

import pytest

from switchboard.scenarios import build_workspace_payload, load_scenarios
from tests.storage_fake import MemoryStorageBridge


@pytest.fixture
def storage_bridge() -> MemoryStorageBridge:
    return MemoryStorageBridge()


@pytest.fixture
def storage(storage_bridge: MemoryStorageBridge):
    storage = storage_bridge.storage(workspace_id="workspace-one")
    storage.reset_workspace(
        payload=build_workspace_payload(
            scenario_id="baseline",
            selected_scenario=load_scenarios()["baseline"],
            identity_mode="eval",
            updated_at=datetime(2026, 9, 19, tzinfo=timezone.utc),
        )
    )
    return storage
