import httpx
import logging
from app.config.settings import settings
from typing import Any, Dict, Optional
from tenacity import (
    retry, stop_after_attempt, wait_exponential,
    retry_if_exception_type,
)

logger = logging.getLogger(__name__)

# Retry on network/timeout errors and 5xx server errors
_RETRYABLE = (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout)



class VirtualLeagueClient:
    def __init__(self):
        self.base_url = "https://hg-event-api-prod.sporty-tech.net/api/instantleagues"
        self.headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en,fr",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Referer": "https://bet261.mg/"
        }
        self.client = httpx.AsyncClient(headers=self.headers, timeout=settings.REQUEST_TIMEOUT_SECONDS)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(_RETRYABLE),
        reraise=True,
    )
    async def _get_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """GET request — retries on network errors and 5xx only."""
        response = await self.client.get(url, params=params)
        if response.status_code >= 500:
            response.raise_for_status()   # triggers retry
        response.raise_for_status()       # 4xx → immediate error, no retry
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
