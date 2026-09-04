import httpx
import logging
import random
from app.config.settings import settings
from typing import Any, Dict, Optional
from tenacity import (
    retry, stop_after_attempt, wait_exponential,
    retry_if_exception_type, retry_if_result,
)

logger = logging.getLogger(__name__)

# Retry on network/timeout errors and 5xx server errors
_RETRYABLE = (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout)


class PermanentError(Exception):
    """Raised for non-retryable HTTP errors (4xx except 429).
    Callers can catch this to skip retry loops."""
    pass


def _is_rate_limited(response: httpx.Response) -> bool:
    """Check if response is a rate-limit (429) or server overload (503)."""
    return response.status_code in (429, 503)


class VirtualLeagueClient:
    def __init__(self):
        self.base_url = "https://hg-event-api-prod.sporty-tech.net/api/instantleagues"
        self.headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en,fr",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Referer": "https://bet261.mg/"
        }
        self.client = httpx.AsyncClient(
            headers=self.headers,
            timeout=settings.REQUEST_TIMEOUT_SECONDS,
            limits=httpx.Limits(
                max_connections=10,
                max_keepalive_connections=5,
                keepalive_expiry=30
            ),
        )

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type(_RETRYABLE),
        reraise=True,
    )
    async def _get_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """GET request — retries on network errors, 429/503, and 5xx.
        
        Raises PermanentError on 4xx client errors (except 429) so callers
        can bail out of retry loops immediately.
        """
        response = await self.client.get(url, params=params)
        
        # Rate limited (429) or server overload (503) — retry with backoff
        if _is_rate_limited(response):
            retry_after = response.headers.get("Retry-After")
            wait_time = float(retry_after) if retry_after else None
            if wait_time is None:
                wait_time = 5 + random.uniform(0, 5)
            logger.warning(
                f"Rate limited ({response.status_code}) on {url}, "
                f"waiting {wait_time:.1f}s before retry"
            )
            import asyncio
            await asyncio.sleep(wait_time)
            response.raise_for_status()  # triggers retry
        
        # 5xx server errors — retry
        if response.status_code >= 500:
            logger.warning(f"Server error ({response.status_code}) on {url}")
            response.raise_for_status()
        
        # 4xx client errors (except 429) — permanent, don't retry
        if 400 <= response.status_code < 500:
            raise PermanentError(
                f"Client error '{response.status_code} {response.reason_phrase}' "
                f"for url {url}"
            )
        
        return response.json()

    async def get_matches(self) -> Dict[str, Any]:
        """Fetch the upcoming matches data."""
        url = f"{self.base_url}/{settings.LEAGUE_ID}/matches"
        return await self._get_json(url)

    async def get_results(self, skip: int = 0, take: int = 50) -> Dict[str, Any]:
        """Fetch the completed matches results."""
        url = f"{self.base_url}/{settings.LEAGUE_ID}/results"
        params = {"skip": skip, "take": take}
        return await self._get_json(url, params=params)

    async def get_ranking(self) -> Dict[str, Any]:
        """Fetch the league ranking standings."""
        url = f"{self.base_url}/{settings.LEAGUE_ID}/ranking"
        return await self._get_json(url)

    async def get_playout(self, round_number: int, event_category_id: int) -> Dict[str, Any]:
        """Fetch playout/goal events for a specific round.

        Args:
            round_number: The round number to fetch playout data for.
            event_category_id: The event category ID for the round (required).
        """
        url = f"{self.base_url}/round/{round_number}/playout"
        params = {
            "eventCategoryId": event_category_id,
            "parentEventCategoryId": settings.LEAGUE_ID
        }
        return await self._get_json(url, params=params)

    async def close(self):
        """Close the async client session."""
        await self.client.aclose()
