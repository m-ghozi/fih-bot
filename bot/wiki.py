"""Small client for the Official Fisch Wiki MediaWiki API."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import aiohttp

from .parsing import clean_extract, clean_wikitext, strip_html

__all__ = ["WikiClient", "WikiError", "PageNotFoundError", "SearchResult", "PageInfo"]

_CACHE_LIMIT = 512


class WikiError(Exception):
    """Raised when communication with the wiki fails."""


class PageNotFoundError(WikiError):
    """Raised when the requested page does not exist."""


@dataclass(frozen=True)
class SearchResult:
    title: str
    snippet: str
    url: str


@dataclass(frozen=True)
class PageInfo:
    title: str
    url: str
    extract: str
    thumbnail: str | None
    missing: bool


class WikiClient:
    def __init__(
        self,
        api_url: str,
        user_agent: str,
        *,
        base_url: str = "https://fischipedia.org/wiki/",
        timeout: float = 15.0,
        ttl: float = 300.0,
    ) -> None:
        self.api_url = api_url
        self.base_url = base_url
        self.user_agent = user_agent
        self.timeout = timeout
        self.ttl = ttl

        self._session: aiohttp.ClientSession | None = None
        self._cache: dict[str, tuple[float, Any]] = {}
        self._semaphore = asyncio.Semaphore(5)

    # ------------------------------------------------------------------ HTTP

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"User-Agent": self.user_agent, "Accept": "application/json"}
            )
        return self._session

    def _cache_get(self, key: str) -> Any | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at < time.monotonic():
            self._cache.pop(key, None)
            return None
        return value

    def _cache_set(self, key: str, value: Any) -> None:
        if len(self._cache) >= _CACHE_LIMIT:
            now = time.monotonic()
            self._cache = {k: v for k, v in self._cache.items() if v[0] > now}
            if len(self._cache) >= _CACHE_LIMIT:
                self._cache.clear()
        self._cache[key] = (time.monotonic() + self.ttl, value)

    async def _request(self, params: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "format": "json",
            "formatversion": "2",
            "maxlag": "5",
            **params,
        }
        key = json.dumps(payload, sort_keys=True, default=str)
        cached = self._cache_get(key)
        if cached is not None:
            return cached

        last_error: Exception | None = None
        async with self._semaphore:
            for attempt in range(3):
                try:
                    session = await self._get_session()
                    timeout = aiohttp.ClientTimeout(total=self.timeout)
                    async with session.get(self.api_url, params=payload, timeout=timeout) as resp:
                        if resp.status == 429:
                            raise WikiError("The wiki is rate limiting requests (HTTP 429). Try again later.")
                        if resp.status >= 500:
                            raise WikiError(f"The wiki is having issues (HTTP {resp.status}).")
                        resp.raise_for_status()
                        data = await resp.json(content_type=None)
                    break
                except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
                    last_error = exc
                    if attempt == 2:
                        raise WikiError(f"Could not reach the wiki: {exc}") from exc
                    await asyncio.sleep(0.6 * (attempt + 1))

        if not isinstance(data, dict):
            raise WikiError("The wiki returned an invalid response.")
        if "error" in data:
            code = data["error"].get("code") or ""
            info = data["error"].get("info") or code or "unknown error"
            if code in {"missingtitle", "nosuchpageid"}:
                raise PageNotFoundError(f"Page not found: {info}")
            raise WikiError(f"Wiki API: {info}")

        self._cache_set(key, data)
        return data

    async def ping(self) -> float:
        """Return the wiki API round-trip time in milliseconds."""
        payload = {
            "format": "json",
            "formatversion": "2",
            "action": "query",
            "meta": "siteinfo",
        }
        start = time.perf_counter()
        async with self._semaphore:
            try:
                session = await self._get_session()
                timeout = aiohttp.ClientTimeout(total=self.timeout)
                async with session.get(
                    self.api_url, params=payload, timeout=timeout
                ) as resp:
                    resp.raise_for_status()
                    await resp.json(content_type=None)
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
                raise WikiError(f"Could not reach the wiki: {exc}") from exc
        return (time.perf_counter() - start) * 1000

    # --------------------------------------------------------------- helpers

    def page_url(self, title: str) -> str:
        return self.base_url + quote(title.replace(" ", "_"))

    # ------------------------------------------------------------------- API

    async def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        data = await self._request(
            {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": min(max(limit, 1), 20),
                "srprop": "snippet",
            }
        )
        results = data.get("query", {}).get("search", []) or []
        output: list[SearchResult] = []
        for item in results:
            title = item.get("title", "").strip()
            if not title:
                continue
            output.append(
                SearchResult(
                    title=title,
                    snippet=strip_html(item.get("snippet", "")),
                    url=self.page_url(title),
                )
            )
        return output

    async def page(self, title: str) -> PageInfo:
        data = await self._request(
            {
                "action": "query",
                "titles": title,
                "redirects": 1,
                "prop": "extracts|pageimages",
                "explaintext": 1,
                "exsectionformat": "plain",
                "pithumbsize": 320,
            }
        )
        pages = data.get("query", {}).get("pages", []) or []
        if not pages:
            raise PageNotFoundError(f"Page '{title}' was not found.")
        page = pages[0]
        resolved_title = page.get("title", title)
        if page.get("missing"):
            return PageInfo(
                title=resolved_title,
                url=self.page_url(resolved_title),
                extract="",
                thumbnail=None,
                missing=True,
            )
        thumbnail = (page.get("thumbnail") or {}).get("source")
        return PageInfo(
            title=resolved_title,
            url=self.page_url(resolved_title),
            extract=clean_extract(page.get("extract", "")),
            thumbnail=thumbnail,
            missing=False,
        )

    async def wikitext(self, title: str) -> tuple[str, str]:
        """Return ``(title_after_redirect, wikitext)``."""
        data = await self._request(
            {
                "action": "parse",
                "page": title,
                "prop": "wikitext",
                "redirects": 1,
            }
        )
        parsed = data.get("parse")
        if not parsed:
            raise PageNotFoundError(f"Page '{title}' was not found.")
        return parsed.get("title", title), parsed.get("wikitext", "")

    async def resolve_page(
        self, query: str, *, suffix: str | None = None
    ) -> tuple[str, str] | None:
        """Resolve a partial name to ``(title, wikitext)`` using search.

        Returns ``None`` when no page matches.
        """
        try:
            return await self.wikitext(query)
        except PageNotFoundError:
            pass

        candidates = [query]
        if suffix and not query.lower().rstrip().endswith(suffix.lower()):
            candidates.append(f"{query} {suffix}")

        seen: set[str] = set()
        for candidate in candidates:
            results = await self.search(candidate, limit=5)
            for result in results:
                if result.title in seen:
                    continue
                seen.add(result.title)
                try:
                    return await self.wikitext(result.title)
                except PageNotFoundError:
                    continue
        return None

    async def category_members(self, category: str, limit: int | str = "max") -> list[str]:
        data = await self._request(
            {
                "action": "query",
                "list": "categorymembers",
                "cmtitle": f"Category:{category}",
                "cmlimit": limit,
                "cmnamespace": 0,
            }
        )
        members = data.get("query", {}).get("categorymembers", []) or []
        return [member["title"] for member in members if member.get("title")]

    async def thumbnail(self, title: str) -> str | None:
        data = await self._request(
            {
                "action": "query",
                "titles": title,
                "redirects": 1,
                "prop": "pageimages",
                "pithumbsize": 320,
            }
        )
        pages = data.get("query", {}).get("pages", []) or []
        if not pages:
            return None
        return (pages[0].get("thumbnail") or {}).get("source")

    async def summary(self, title: str, limit: int = 400) -> str:
        info = await self.page(title)
        text = clean_wikitext(info.extract)
        if len(text) <= limit:
            return text
        return text[: limit - 1].rsplit(" ", 1)[0] + "…"

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
