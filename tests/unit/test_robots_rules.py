from gamecrafter.infrastructure.ingestion.robots import RobotsRules


def test_robots_rules_apply_only_to_the_same_origin() -> None:
    rules = RobotsRules(
        origin="https://nte.perfectworld.com",
        text="User-agent: GameCrafter\nDisallow: /en/private/\nAllow: /en/\n",
    )

    assert rules.can_fetch("https://nte.perfectworld.com/en/main.html")
    assert not rules.can_fetch("https://nte.perfectworld.com/en/private/secret.html")
    assert not rules.can_fetch("https://evil.example/en/main.html")
