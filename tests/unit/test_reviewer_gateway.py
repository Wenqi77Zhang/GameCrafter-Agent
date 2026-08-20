import json
from uuid import UUID

import pytest

from gamecrafter.application.ports.model_gateway import InvalidModelOutputError
from gamecrafter.application.ports.review_gateway import KnowledgeReviewRequest, ReviewCandidate
from gamecrafter.infrastructure.models.reviewer import OllamaKnowledgeReviewerGateway

CLAIM_ID = UUID("00000000-0000-0000-0000-000000000456")
EXTRACTION_ID = UUID("00000000-0000-0000-0000-000000000123")


def request() -> KnowledgeReviewRequest:
    return KnowledgeReviewRequest(
        extraction_run_id=EXTRACTION_ID,
        subject_entity_key="game:nte",
        candidates=(
            ReviewCandidate(
                claim_id=CLAIM_ID,
                predicate="game.developer",
                value_kind="string",
                value="Hotta Studio",
                evidence_quotes=("Developed by Hotta Studio.",),
            ),
        ),
    )


def test_local_reviewer_requires_exact_ids_and_records_safe_usage() -> None:
    captured: dict[str, object] = {}

    def requester(payload: dict[str, object]) -> dict[str, object]:
        captured.update(payload)
        return {
            "created_at": "2026-08-21T00:00:00Z",
            "message": {
                "content": json.dumps(
                    {
                        "decisions": [
                            {
                                "claim_id": str(CLAIM_ID),
                                "decision": "agent_approved",
                                "suggested_predicate": None,
                                "priority": 90,
                                "reason_code": "direct_support",
                                "rationale": "The quote directly identifies the developer.",
                                "risk_codes": [],
                            }
                        ]
                    }
                )
            },
            "prompt_eval_count": 20,
            "eval_count": 10,
        }

    result = OllamaKnowledgeReviewerGateway(model="qwen3.5:4b", requester=requester).review(
        request()
    )

    assert result.provider == "ollama-local"
    assert result.usage.total_tokens == 30
    assert result.decisions[0].claim_id == CLAIM_ID
    assert captured["think"] is False
    assert captured["stream"] is False


def test_local_reviewer_fails_closed_on_invented_claim_id() -> None:
    def requester(payload: dict[str, object]) -> dict[str, object]:
        del payload
        return {
            "message": {
                "content": json.dumps(
                    {
                        "decisions": [
                            {
                                "claim_id": "00000000-0000-0000-0000-000000000999",
                                "decision": "agent_rejected",
                                "suggested_predicate": None,
                                "priority": 0,
                                "reason_code": "unsupported",
                                "rationale": "Unsupported.",
                                "risk_codes": ["unsupported"],
                            }
                        ]
                    }
                )
            }
        }

    with pytest.raises(InvalidModelOutputError, match="claim IDs"):
        OllamaKnowledgeReviewerGateway(model="qwen3.5:4b", requester=requester).review(request())
