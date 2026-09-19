"""Calibrate the live policy-faithfulness judge with pytest and LangSmith."""

from pathlib import Path

import pytest
from dotenv import load_dotenv
from langsmith import testing

from switchboard.agent import create_model
from switchboard.evaluation_cases import (
    PolicyFaithfulnessEvaluationCase,
    load_policy_faithfulness_evaluation_cases,
)
from switchboard.policy_evaluation import evaluate_policy

ROOT = Path(__file__).resolve().parent.parent
EVALUATION_CASES = load_policy_faithfulness_evaluation_cases()


@pytest.mark.langsmith(test_suite_name="Switchboard policy faithfulness evals")
@pytest.mark.parametrize(
    "evaluation_case", EVALUATION_CASES, ids=[case.id for case in EVALUATION_CASES]
)
def test_policy_judge_matches_reference_expectation(
    evaluation_case: PolicyFaithfulnessEvaluationCase,
) -> None:
    """Compare one live judge result with its withheld expected classification."""
    # 1. Record the case without exposing its expectation to the model.
    load_dotenv(ROOT / ".env")
    testing.log_inputs({"claims": evaluation_case.claims})
    testing.log_reference_outputs({"expect_issue": evaluation_case.expect_issue})

    # 2. Run the real judge and record its validated output.
    review = evaluate_policy(claims=evaluation_case.claims, model=create_model())
    testing.log_outputs(review.model_dump(mode="json"))

    # 3. Score whether the judge agreed with the withheld classification.
    matches_expectation = bool(review.issues) == evaluation_case.expect_issue
    testing.log_feedback(key="expected_classification", score=matches_expectation)
    assert matches_expectation
