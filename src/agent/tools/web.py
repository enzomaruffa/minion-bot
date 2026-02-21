"""Lightweight web tools — search (DuckDuckGo) and URL fetch (readability)."""

import logging

logger = logging.getLogger(__name__)

_MAX_OUTPUT = 4000


def web_search(query: str, max_results: int = 5) -> str:
    """Search the web via DuckDuckGo. Returns titles, URLs, and snippets.

    Args:
        query: Search query string.
        max_results: Maximum number of results to return (default 5).

    Returns:
        Formatted search results with titles, URLs, and snippets.
    """
    try:
        from ddgs import DDGS

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))

        if not results:
            return f"No results found for: {query}"

        lines = [f"Search results for: {query}\n"]
        for i, r in enumerate(results, 1):
            title = r.get("title", "No title")
            url = r.get("href", "")
            snippet = r.get("body", "")
            lines.append(f"{i}. {title}\n   {url}\n   {snippet}\n")

        return "\n".join(lines)
    except Exception as e:
        return f"Search failed: {e}"


def fetch_url(url: str) -> str:
    """Fetch a URL and extract main text content via readability.

    Args:
        url: The URL to fetch.

    Returns:
        Extracted main text content, truncated to 4000 chars.
    """
    try:
        import httpx
        from lxml.html.clean import Cleaner
        from readability import Document

        resp = httpx.get(url, follow_redirects=True, timeout=30)
        resp.raise_for_status()

        doc = Document(resp.text)
        title = doc.title()

        # Extract readable HTML, then strip tags for plain text
        summary_html = doc.summary()
        cleaner = Cleaner(scripts=True, javascript=True, style=True)
        cleaned = cleaner.clean_html(summary_html)

        # Simple tag stripping for plain text
        import re

        text = re.sub(r"<[^>]+>", "", cleaned)
        text = re.sub(r"\s+", " ", text).strip()

        output = f"Title: {title}\nURL: {url}\n\n{text}"
        if len(output) > _MAX_OUTPUT:
            output = output[:_MAX_OUTPUT] + "\n... (truncated)"
        return output
    except Exception as e:
        return f"Failed to fetch {url}: {e}"
