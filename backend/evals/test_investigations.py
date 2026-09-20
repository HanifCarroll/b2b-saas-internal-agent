"""Run live investigation evaluations with pytest and LangSmith."""

from pathlib import Path
from uuid import uuid4

import pytest
from dotenv import load_dotenv
from langsmith import testing

from switchboard.demo.setup import reset_demo
from switchboard.investigation.agent import create_model
from switchboard.investigation.evaluation_cases import (
    load_investigation_evaluation_cases,
)
from switchboard.investigation.runner import investigate_scenario
from switchboard.storage import WorkspaceStorage

ROOT = Path(__file__).resolve().parent.parent
EVALUATION_CASES = load_investigation_evaluation_cases()


@pytest.mark.langsmith(test_suite_name="Switchboard investigation evals")
@pytest.mark.parametrize("case_id", EVALUATION_CASES, ids=EVALUATION_CASES)
def test_investigation_reaches_expected_outcome(case_id: str) -> None:
    """Run one isolated live-model case and record its evaluation evidence."""
    # 1. Prepare isolated business records for this evaluation case.
    load_dotenv(ROOT / ".env")
    evaluation_case = EVALUATION_CASES[case_id]
    storage = WorkspaceStorage.from_environment(
        workspace_id=f"eval-{case_id}-{uuid4()}"
    )
    reset_demo(
        storage=storage,
        scenario_id=evaluation_case.scenario_id,
        identity_mode="eval",
    )

    testing.log_inputs({"scenario_id": evaluation_case.scenario_id})
    testing.log_reference_outputs(
        {
            "outcome": evaluation_case.expected_outcome,
            "criteria": evaluation_case.criteria,
        }
    )

    # 2. Run the real agent and record the validated application result.
    run = investigate_scenario(
        scenario_id=evaluation_case.scenario_id,
        model=create_model(),
        storage=storage,
    )
    investigation = run.result.investigation
    testing.log_outputs(investigation.model_dump(mode="json"))

    # 3. Score the deterministic outcome; inspect qualitative criteria in LangSmith.
    outcome_matches = investigation.outcome == evaluation_case.expected_outcome
    testing.log_feedback(key="expected_outcome", score=outcome_matches)
    assert outcome_matches
