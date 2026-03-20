"""Pluggable web search for grounding xBrain pipeline in real-time data.

Each search provider implements ``search(query, max_results) -> list[SearchResult]``.
The ``SearchAggregator`` fans queries out to all enabled providers and
deduplicates by URL.

Adding a new provider:
  1. Subclass ``SearchProvider``
  2. Implement ``search()`` → list[SearchResult]
  3. Register it in ``SearchAggregator.from_config()``
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from xbrain.log import log as _log


# ── Result type ──────────────────────────────────────────────────────

@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str  # provider name, e.g. "duckduckgo", "hackernews"


# ── Base class ───────────────────────────────────────────────────────

class SearchProvider:
    """Abstract base for a search provider."""
    name: str = "base"

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        raise NotImplementedError


# ── DuckDuckGo (free, no API key) ────────────────────────────────────

class DuckDuckGoProvider(SearchProvider):
    name = "duckduckgo"

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        try:
            from ddgs import DDGS
        except ImportError:
            try:
                from duckduckgo_search import DDGS
            except ImportError:
                return []

        results: list[SearchResult] = []
        try:
            ddgs = DDGS()
            for r in ddgs.text(query, max_results=max_results):
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("href", ""),
                    snippet=r.get("body", ""),
                    source=self.name,
                ))
        except Exception:
            pass  # Search is best-effort; never break the pipeline
        return results


# ── HackerNews Algolia (free, no API key) ────────────────────────────

class HackerNewsProvider(SearchProvider):
    name = "hackernews"

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        try:
            import urllib.request
            import json as _json
        except ImportError:
            return []

        results: list[SearchResult] = []
        try:
            encoded = urllib.parse.quote_plus(query)
            api_url = f"https://hn.algolia.com/api/v1/search?query={encoded}&tags=story&hitsPerPage={max_results}"
            req = urllib.request.Request(api_url, headers={"User-Agent": "xBrain/1.7"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = _json.loads(resp.read().decode())
            for hit in data.get("hits", [])[:max_results]:
                title = hit.get("title", "")
                hn_url = f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"
                # Use comment text or title as snippet
                snippet = (hit.get("story_text") or hit.get("title") or "")[:300]
                points = hit.get("points", 0)
                comments = hit.get("num_comments", 0)
                results.append(SearchResult(
                    title=title,
                    url=hn_url,
                    snippet=f"[{points} pts, {comments} comments] {snippet}",
                    source=self.name,
                ))
        except Exception:
            pass  # Best-effort
        return results


# ── Aggregator ───────────────────────────────────────────────────────


class SearchAggregator:
    """Fans queries to all enabled providers, deduplicates results."""

    def __init__(self, providers: list[SearchProvider] | None = None):
        self.providers: list[SearchProvider] = providers or []

    @classmethod
    def from_config(cls) -> SearchAggregator:
        """Auto-detect available providers and enable them."""
        providers: list[SearchProvider] = []

        # DuckDuckGo — only enable if package is installed
        try:
            import duckduckgo_search  # noqa: F401
            providers.append(DuckDuckGoProvider())
        except ImportError:
            try:
                import ddgs  # noqa: F401
                providers.append(DuckDuckGoProvider())
            except ImportError:
                pass

        # HackerNews — always available (uses stdlib urllib)
        providers.append(HackerNewsProvider())

        return cls(providers=providers)

    @property
    def enabled(self) -> bool:
        return len(self.providers) > 0

    @property
    def provider_names(self) -> list[str]:
        return [p.name for p in self.providers]

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        """Search all providers, deduplicate by URL, return combined results."""
        all_results: list[SearchResult] = []
        seen_urls: set[str] = set()

        for provider in self.providers:
            try:
                results = provider.search(query, max_results=max_results)
                for r in results:
                    if r.url not in seen_urls:
                        seen_urls.add(r.url)
                        all_results.append(r)
            except Exception:
                pass  # Never let search failures break the pipeline

        return all_results

    def search_many(self, queries: list[str], max_results_per_query: int = 3) -> list[SearchResult]:
        """Run multiple queries, deduplicate across all."""
        all_results: list[SearchResult] = []
        seen_urls: set[str] = set()

        for query in queries:
            results = self.search(query, max_results=max_results_per_query)
            for r in results:
                if r.url not in seen_urls:
                    seen_urls.add(r.url)
                    all_results.append(r)
            # Small delay between queries to be respectful
            if len(queries) > 1:
                time.sleep(0.5)

        return all_results


def format_search_results(results: list[SearchResult], max_chars: int = 3000) -> str:
    """Format search results into a compact text block for LLM context injection."""
    if not results:
        return ""

    lines: list[str] = []
    total_len = 0

    for r in results:
        entry = f"- [{r.source}] {r.title}: {r.snippet}"
        if total_len + len(entry) > max_chars:
            break
        lines.append(entry)
        total_len += len(entry)

    return "\n".join(lines)
