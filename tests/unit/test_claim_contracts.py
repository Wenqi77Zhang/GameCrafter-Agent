import pytest

from gamecrafter.domain.knowledge.claims import (
    CandidateClaim,
    ClaimValueKind,
    EvidenceSpan,
    FactPredicate,
)


def test_candidate_claim_requires_typed_value_and_exact_evidence() -> None:
    evidence = EvidenceSpan(
        start_offset=10,
        end_offset=30,
        quote="Official game evidence",
    )
    claim = CandidateClaim(
        predicate=FactPredicate.GAME_DEVELOPER,
        value_kind=ClaimValueKind.ENTITY_REF,
        value={"entity_key": "organization:hotta-studio"},
        confidence=0.875,
        evidence=(evidence,),
    )

    assert len(evidence.quote_sha256) == 64
    assert claim.predicate is FactPredicate.GAME_DEVELOPER


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        (ClaimValueKind.STRING, ""),
        (ClaimValueKind.NUMBER, True),
        (ClaimValueKind.BOOLEAN, "true"),
        (ClaimValueKind.ENTITY_REF, {"name": "Hotta Studio"}),
        (ClaimValueKind.STRING_LIST, []),
    ],
)
def test_candidate_claim_rejects_invalid_value_shapes(
    kind: ClaimValueKind,
    value: object,
) -> None:
    with pytest.raises(ValueError):
        CandidateClaim(
            predicate=FactPredicate.UNCLASSIFIED,
            value_kind=kind,
            value=value,
            confidence=0.5,
            evidence=(EvidenceSpan(0, 4, "text"),),
        )


def test_candidate_claim_cannot_exist_without_evidence() -> None:
    with pytest.raises(ValueError, match="at least one evidence"):
        CandidateClaim(
            predicate=FactPredicate.GAME_NAME,
            value_kind=ClaimValueKind.STRING,
            value="Neverness to Everness",
            confidence=0.9,
            evidence=(),
        )
