from gamecrafter.domain.knowledge.claims import ConflictRelation, FactPredicate
from gamecrafter.domain.knowledge.conflicts import (
    CONFLICT_POLICY_VERSION,
    EXCLUSIVE_PREDICATES,
    classify_predicate,
)


def test_exclusive_predicates_are_versioned_and_classified_as_conflicting() -> None:
    assert {
        FactPredicate.GAME_NAME,
        FactPredicate.RELEASE_STATUS,
        FactPredicate.RELEASE_DATE,
        FactPredicate.GENRE_PRIMARY,
    } == EXCLUSIVE_PREDICATES
    classified = classify_predicate(FactPredicate.GAME_NAME)
    assert classified.relation is ConflictRelation.CONFLICTING
    assert classified.policy_version == CONFLICT_POLICY_VERSION
    assert CONFLICT_POLICY_VERSION in classified.basis


def test_nonexclusive_predicates_fail_conservatively_to_possible_coexistence() -> None:
    for predicate in (FactPredicate.GAME_DEVELOPER, FactPredicate.GAME_ALIAS):
        classified = classify_predicate(predicate)
        assert classified.relation is ConflictRelation.POSSIBLY_COEXISTING
        assert "human review" in classified.basis
