import pytest

from gamecrafter.domain.knowledge.sources import EvidenceDigest, SourceType


def test_evidence_digest_normalizes_valid_sha256() -> None:
    digest = EvidenceDigest("A" * 64)

    assert digest.value == "a" * 64


@pytest.mark.parametrize(
    "value",
    [
        "",
        "a" * 63,
        "a" * 65,
        "g" * 64,
    ],
)
def test_evidence_digest_rejects_non_sha256_values(value: str) -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        EvidenceDigest(value)


def test_source_type_contract_contains_public_and_private_evidence_categories() -> None:
    assert {source_type.value for source_type in SourceType} == {
        "overview",
        "character",
        "world",
        "gameplay",
        "news",
        "update",
        "event",
        "guide_faq",
        "document",
        "transcript",
        "gdd",
        "other",
    }
