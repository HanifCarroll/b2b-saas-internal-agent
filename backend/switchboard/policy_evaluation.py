"""Optional model-based review of policy claims; never authorizes an action."""

import json
from pathlib import Path

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import Field

from switchboard.models import Record, Text
from switchboard.scenarios import FIXTURES


class PolicyIssue(Record):
    claim: Text
    policy_id: Text
    policy_excerpt: Text
    explanation: Text


class PolicyReview(Record):
    issues: list[PolicyIssue]
    limitation: str = Field(default="Model judgment, not proof of correctness.")


def evaluate_policy(*, claims: str, model: BaseChatModel) -> PolicyReview:
    """Compare claims with policy sources in a separate call, without agent history."""
    # 1. Load the source policies and require evidence for evaluation.
    policies = [
        {"id": path.stem, "content": path.read_text()}
        for path in sorted((FIXTURES / "policies").glob("*.md"))
    ]
    if not policies:
        raise ValueError("Policy evaluation requires policy sources")

    # 2. Ask the reviewer model to compare claims with those sources.
    prompt = (Path(__file__).parent / "prompts" / "policy_evaluation.md").read_text()
    response = model.invoke(
        [
            (
                "system",
                prompt
                + "\n\nOutput schema:\n"
                + json.dumps(PolicyReview.model_json_schema()),
            ),
            ("human", json.dumps({"policies": policies, "claims": claims})),
        ],
        config={"run_name": "policy-faithfulness-review"},
    )

    # 3. Validate the response and reject fabricated source excerpts.
    review = PolicyReview.model_validate_json(response.text)
    # Reject invented source citations rather than displaying a fabricated review.
    sources = {policy["id"]: policy["content"] for policy in policies}
    for issue in review.issues:
        source = sources.get(issue.policy_id)
        if source is None or issue.policy_excerpt not in source:
            raise ValueError("Policy review contains an unverified source excerpt")

    return review
