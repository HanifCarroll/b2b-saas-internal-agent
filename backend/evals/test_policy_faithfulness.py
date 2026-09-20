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
    testing.log_reference_outputs(
        {
            "expect_issue": evaluation_case.expect_issue,
            "expected_issue_kinds": evaluation_case.expected_issue_kinds,
            "expected_policy_ids": evaluation_case.expected_policy_ids,
        }
    )

    # 2. Run the real judge and record its validated output.
    review = evaluate_policy(claims=evaluation_case.claims, model=create_model())
    testing.log_outputs(review.model_dump(mode="json"))

    # 3. Score the broad classification and the expected policy findings.
    matches_expectation = bool(review.issues) == evaluation_case.expect_issue

    found_issue_kinds = {issue.issue_kind for issue in review.issues}
    expected_issue_kinds = set(evaluation_case.expected_issue_kinds)
    matches_issue_kinds = found_issue_kinds == expected_issue_kinds

    found_policy_ids = {issue.policy_id for issue in review.issues}
    expected_policy_ids = set(evaluation_case.expected_policy_ids)
    matches_policy_ids = found_policy_ids == expected_policy_ids

    testing.log_feedback(key="expected_classification", score=matches_expectation)
    testing.log_feedback(key="expected_issue_kinds", score=matches_issue_kinds)
    testing.log_feedback(key="expected_policy_ids", score=matches_policy_ids)

    assert matches_expectation
    assert matches_issue_kinds
    assert matches_policy_ids
