"""Optional model-based review of policy claims; never authorizes an action."""

import json
from pathlib import Path

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import Field

from switchboard.integrations.database import FIXTURES
from switchboard.models import Record, Text


class PolicyIssue(Record):
    claim: Text
    policy_id: Text
    policy_excerpt: Text
    explanation: Text


class PolicyReview(Record):
    issues: list[PolicyIssue]
    limitation: str = Field(default="Model judgment, not proof of correctness.")


def evaluate_policy(claims: str, model: BaseChatModel) -> PolicyReview:
    """Compare claims with policy sources in a separate call, without agent history."""
    policies = [
        {"id": path.stem, "content": path.read_text()}
        for path in sorted((FIXTURES / "policies").glob("*.md"))
    ]
    if not policies:
        raise ValueError("Policy evaluation requires policy sources")
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
    review = PolicyReview.model_validate_json(response.text)
    # Reject invented source citations rather than displaying a fabricated review.
    sources = {policy["id"]: policy["content"] for policy in policies}
    for issue in review.issues:
        source = sources.get(issue.policy_id)
        if source is None or issue.policy_excerpt not in source:
            raise ValueError("Policy review contains an unverified source excerpt")
    return review


def main():
    """Calibrate the judge against known good and bad claims using live calls."""
    from dotenv import load_dotenv

    from switchboard.agent import create_model

    root = Path(__file__).resolve().parent.parent
    load_dotenv(root / ".env")
    examples = json.loads(
        (root / "data/evaluations/policy_faithfulness.json").read_text()
    )
    model = create_model()
    disagreements = 0
    for example in examples:
        review = evaluate_policy(example["claims"], model)
        matches = bool(review.issues) == example["expect_issue"]
        if not matches:
            disagreements += 1
        print(
            json.dumps(
                {
                    "case": example["id"],
                    "matches_expected": matches,
                    "review": review.model_dump(),
                }
            )
        )
    raise SystemExit(1 if disagreements else 0)


if __name__ == "__main__":
    main()
