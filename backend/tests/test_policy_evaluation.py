"""Check evaluator parsing and citation validation without paid calls."""

import json

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from pydantic import ValidationError

from switchboard.policy_evaluation import evaluate_policy


def test_policy_review_accepts_no_issues():
    model = GenericFakeChatModel(messages=iter([AIMessage(content='{"issues": []}')]))

    assert (
        evaluate_policy(
            claims="An independent approver is required.", model=model
        ).issues
        == []
    )


def test_policy_review_rejects_invented_excerpt():
    # 1. Set up inputs and exercise the behavior under test.
    review = {
        "issues": [
            {
                "claim": "Never roll back.",
                "policy_id": "endpoint-change-v2",
                "policy_excerpt": "Invented policy text.",
                "issue_kind": "invented_absolute_prohibition",
                "explanation": "Unsupported.",
            }
        ]
    }
    model = GenericFakeChatModel(messages=iter([AIMessage(content=json.dumps(review))]))

    with pytest.raises(ValueError, match="unverified source excerpt"):
        evaluate_policy(claims="Never roll back.", model=model)


def test_policy_review_rejects_unknown_issue_kind():
    review = {
        "issues": [
            {
                "claim": "Never roll back.",
                "policy_id": "endpoint-change-v2",
                "policy_excerpt": "Otherwise, stop for manual intervention.",
                "issue_kind": "unclear_policy_problem",
                "explanation": "The claim turns a conditional rule into a blanket ban.",
            }
        ]
    }
    model = GenericFakeChatModel(messages=iter([AIMessage(content=json.dumps(review))]))

    with pytest.raises(ValidationError):
        evaluate_policy(claims="Never roll back.", model=model)


def test_invalid_judge_output_is_not_a_pass():
    model = GenericFakeChatModel(messages=iter([AIMessage(content="Looks good")]))

    with pytest.raises(ValidationError):
        evaluate_policy(claims="Never roll back.", model=model)
