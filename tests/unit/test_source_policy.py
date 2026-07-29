import pytest

from gamecrafter.infrastructure.ingestion.nte import NTE_ACCESS_RULES
from gamecrafter.security.source_policy import (
    AccessBudget,
    AccessBudgetExceededError,
    AccessPurpose,
    OfficialSourcePolicy,
    SourcePolicyError,
    UnsafeNetworkTargetError,
    UnsupportedSourceError,
    canonicalize_web_url,
)


class FixedResolver:
    def __init__(self, *addresses: str) -> None:
        self.addresses = addresses

    def resolve(self, hostname: str) -> tuple[str, ...]:
        return self.addresses


def public_policy() -> OfficialSourcePolicy:
    return OfficialSourcePolicy(
        NTE_ACCESS_RULES,
        resolver=FixedResolver("8.8.8.8", "2001:4860:4860::8888"),
    )


def test_canonical_url_removes_tracking_but_preserves_meaningful_state() -> None:
    canonical = canonicalize_web_url(
        "HTTPS://NTE.PERFECTWORLD.COM/en/main.html"
        "?utm_source=test&role=1&nav=2&request_id=secret#character"
    )

    assert canonical == "https://nte.perfectworld.com/en/main.html?nav=2&role=1"


@pytest.mark.parametrize(
    "url",
    [
        "http://nte.perfectworld.com/en/main.html",
        "https://user:password@nte.perfectworld.com/en/main.html",
        "https://nte.perfectworld.com:8443/en/main.html",
        "https://nte.perfectworld.com/en/../private",
        "https://nte.perfectworld.com\\@evil.example/en/main.html",
    ],
)
def test_canonical_url_rejects_unsafe_syntax(url: str) -> None:
    with pytest.raises(SourcePolicyError):
        canonicalize_web_url(url)


def test_policy_requires_exact_official_host_and_confirmed_locale_paths() -> None:
    policy = public_policy()

    assert (
        policy.authorize("https://nte.perfectworld.com/en/main.html").rule.site_key == "nte-global"
    )
    with pytest.raises(UnsupportedSourceError):
        policy.authorize("https://nte.perfectworld.com.evil.example/en/main.html")
    with pytest.raises(UnsupportedSourceError):
        policy.authorize("https://nte.perfectworld.com/kr/main.html")
    with pytest.raises(UnsupportedSourceError):
        policy.authorize("https://nte.perfectworld.com/en/private.html")


def test_policy_rechecks_network_resolution_for_ssrf() -> None:
    policy = OfficialSourcePolicy(
        NTE_ACCESS_RULES,
        resolver=FixedResolver("127.0.0.1"),
    )

    with pytest.raises(UnsafeNetworkTargetError, match="non-public"):
        policy.authorize("https://nte.perfectworld.com/en/main.html")


def test_policy_separates_page_asset_and_browser_permissions() -> None:
    policy = public_policy()
    script_url = "https://nte.perfectworld.com/public/app.js"

    with pytest.raises(UnsupportedSourceError):
        policy.authorize(script_url, purpose=AccessPurpose.PAGE)
    assert policy.authorize(script_url, purpose=AccessPurpose.ASSET).url == script_url
    assert policy.browser_fallback_allowed("https://nte.perfectworld.com/en/main.html?nav=2")
    assert not policy.browser_fallback_allowed(
        "https://nte.perfectworld.com/en/article/news/index.html"
    )


def test_access_budget_stops_before_unbounded_requests() -> None:
    budget = AccessBudget(max_requests=2)

    assert budget.consume() == 1
    assert budget.consume() == 2
    with pytest.raises(AccessBudgetExceededError):
        budget.consume()
    assert budget.used_requests == 2


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_requests": 0},
        {"max_requests": 1, "max_redirects_per_request": -1},
        {"max_requests": 1, "max_concurrency_per_host": 0},
        {"max_requests": 1, "min_interval_seconds": -1},
    ],
)
def test_access_budget_rejects_invalid_configuration(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        AccessBudget(**kwargs)
