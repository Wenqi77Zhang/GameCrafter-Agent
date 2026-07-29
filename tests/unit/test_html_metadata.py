from gamecrafter.infrastructure.ingestion.html import parse_html_metadata


def test_html_metadata_parser_is_bounded_and_keeps_alternates() -> None:
    parsed = parse_html_metadata(
        """
        <html lang="en">
          <head>
            <title>NTE News</title>
            <meta property="article:published_time" content="2026-07-08">
            <link rel="alternate" hreflang="ja" href="/jp/article.html">
          </head>
          <body>
            <a href="/one"><span>First</span> article</a>
            <a href="/two">Second article</a>
          </body>
        </html>
        """,
        max_links=1,
    )

    assert parsed.title == "NTE News"
    assert parsed.document_language == "en"
    assert parsed.metadata["article:published_time"] == "2026-07-08"
    assert parsed.links[0].text == "First article"
    assert len(parsed.links) == 1
    assert parsed.alternates[0].language == "ja"
