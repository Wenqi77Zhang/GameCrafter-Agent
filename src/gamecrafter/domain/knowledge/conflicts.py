"""Versioned deterministic classification for candidate-claim disagreements."""

from __future__ import annotations

from dataclasses import dataclass

from gamecrafter.domain.knowledge.claims import ConflictRelation, FactPredicate

CONFLICT_POLICY_VERSION = "claim-conflict-v1"

# These predicates describe one primary value inside the already fingerprinted locale, region,
# effective-time, and game-version scope. Every other predicate is treated conservatively as
# possibly coexisting so automation never invents exclusivity.
EXCLUSIVE_PREDICATES = frozenset(
    {
        FactPredicate.GAME_NAME,
        FactPredicate.RELEASE_STATUS,
        FactPredicate.RELEASE_DATE,
        FactPredicate.GENRE_PRIMARY,
    }
)


@dataclass(frozen=True, slots=True)
class ConflictClassification:
    """Explainable relation stored on every member of one comparison group."""

    relation: ConflictRelation
    basis: str
    policy_version: str = CONFLICT_POLICY_VERSION


def classify_predicate(predicate: FactPredicate) -> ConflictClassification:
    """Classify differing values without model judgment or confidence ranking."""

    if predicate in EXCLUSIVE_PREDICATES:
        return ConflictClassification(
            relation=ConflictRelation.CONFLICTING,
            basis=(
                f"{CONFLICT_POLICY_VERSION}: predicate is single-valued inside the exact "
                "locale, region, effective-time, and game-version scope"
            ),
        )
    return ConflictClassification(
        relation=ConflictRelation.POSSIBLY_COEXISTING,
        basis=(
            f"{CONFLICT_POLICY_VERSION}: differing values may coexist; human review must decide "
            "whether they describe separate supported facts"
        ),
    )
