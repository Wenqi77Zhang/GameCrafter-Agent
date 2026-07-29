from datetime import UTC, datetime

import pytest

from gamecrafter.domain.knowledge.sources import SourceType
from gamecrafter.infrastructure.ingestion.nte import NteSiteAdapter
from gamecrafter.security.source_policy import SourcePolicyError


def test_global_adapter_discovers_and_classifies_official_articles() -> None:
    html = """
    <html lang="en">
      <body>
        <a href="/en/article/news/gameevent/20260703/262998.html">
          NTE Version 1.2 Creation Event <span>2026-07-08</span>
        </a>
        <a href="/en/article/news/gamenews/20260706/263001.html">
          Version 1.2 Update Notes <time>2026-07-06</time>
        </a>
        <a href="/en/article/news/gamebroad/20260426/261931.html">
          NTE Launch FAQ <time>2026-04-27</time>
        </a>
        <a href="/en/article/news/index1.html">2</a>
        <a href="https://evil.example/trap">External</a>
      </body>
    </html>
    """
    adapter = NteSiteAdapter()

    candidates = adapter.discover(
        html,
        page_url="https://nte.perfectworld.com/en/article/news/index.html",
    )

    assert len(candidates) == 3
    assert [candidate.source_type for candidate in candidates] == [
        SourceType.EVENT,
        SourceType.UPDATE,
        SourceType.GUIDE_FAQ,
    ]
    assert candidates[0].published_at == datetime(2026, 7, 8, tzinfo=UTC)
    assert candidates[0].family_signal == "gameevent:path-date:20260703"
    assert candidates[1].classification_basis == "title rule: version, maintenance, or update"
    assert candidates[2].classification_basis == "title rule: guide or FAQ"


def test_mainland_adapter_uses_desktop_identity_for_mobile_articles() -> None:
    adapter = NteSiteAdapter(mainland=True)
    mobile_url = "https://yh.wanmei.com/m/news/gamebroad/20260426/261929.html"

    assert adapter.canonicalize(mobile_url) == (
        "https://yh.wanmei.com/news/gamebroad/20260426/261929.html"
    )
    html = f"""
    <a href="{mobile_url}">《异环》关于近期异常问题的补偿说明 2026-04-26</a>
    """
    candidates = adapter.discover(
        html,
        page_url="https://yh.wanmei.com/news/index4.html",
    )

    assert len(candidates) == 1
    assert candidates[0].locale == "zh-CN"
    assert candidates[0].region == "CN"
    assert candidates[0].site_key == "nte-mainland-cn"
    assert candidates[0].canonical_url == (
        "https://yh.wanmei.com/news/gamebroad/20260426/261929.html"
    )


def test_adapter_removes_homepage_ui_state_and_limits_browser_fallback() -> None:
    global_adapter = NteSiteAdapter()
    mainland_adapter = NteSiteAdapter(mainland=True)

    assert global_adapter.canonicalize(
        "https://nte.perfectworld.com/en/main.html?nav=2&role=1"
    ) == ("https://nte.perfectworld.com/en/main.html")
    assert mainland_adapter.canonicalize(
        "https://yh.wanmei.com/main.html?nav=1&utm_source=test"
    ) == ("https://yh.wanmei.com/main.html")
    assert global_adapter.browser_fallback_allowed("https://nte.perfectworld.com/jp/main.html")
    assert not global_adapter.browser_fallback_allowed(
        "https://nte.perfectworld.com/en/article/news/index.html"
    )


def test_adapter_does_not_infer_publication_date_from_url_path() -> None:
    adapter = NteSiteAdapter()
    html = """
    <a href="/en/article/news/gamenews/20260428/261950.html">
      NTE Officially Launched
    </a>
    """

    candidate = adapter.discover(
        html,
        page_url="https://nte.perfectworld.com/en/article/news/index.html",
    )[0]

    assert candidate.published_at is None
    assert candidate.family_signal == "gamenews:path-date:20260428"


def test_adapter_normalizes_direct_homepage_and_article_imports() -> None:
    adapter = NteSiteAdapter()

    homepage = adapter.adapt(
        "https://nte.perfectworld.com/en/main.html?role=1",
        title="Neverness to Everness",
    )
    article = adapter.adapt(
        "https://nte.perfectworld.com/en/article/news/gamenews/20260706/263001.html",
        title="Version 1.2 Update Notes",
    )

    assert homepage.canonical_url == "https://nte.perfectworld.com/en/main.html"
    assert homepage.source_type is SourceType.OVERVIEW
    assert homepage.classification_basis == "official homepage path"
    assert article.source_type is SourceType.UPDATE
    assert article.raw_category == "gamenews"
    assert article.family_signal == "gamenews:path-date:20260706"


def test_adapter_rejects_listing_as_direct_evidence_and_unknown_paths() -> None:
    adapter = NteSiteAdapter()
    listing = "https://nte.perfectworld.com/en/article/news/index.html"

    assert adapter.supports(listing)
    assert not adapter.supports("https://nte.perfectworld.com/en/unknown.html")
    with pytest.raises(SourcePolicyError, match="discovery inputs"):
        adapter.adapt(listing, title="News")
