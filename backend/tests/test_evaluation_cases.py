"""Keep live-model evaluation references aligned with scenario setup."""

from switchboard.demo.scenarios import load_scenarios
from switchboard.investigation.evaluation_cases import (
    load_investigation_evaluation_cases,
)


def test_every_investigation_scenario_has_one_evaluation_case():
    scenarios = load_scenarios()
    evaluation_cases = load_investigation_evaluation_cases()

    assert set(evaluation_cases) == set(scenarios)
    assert all(
        case.scenario_id == case_id for case_id, case in evaluation_cases.items()
    )
