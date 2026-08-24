import httpx
from app.config.settings import settings
from typing import Any, Dict

class VirtualLeagueClient:
    def __init__(self):
        # The base URL discovered from the Playwright run
        self.base_url = "https://hg-event-api-prod.sporty-tech.net/api/instantleagues"
        self.headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en,fr",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Referer": "https://bet261.mg/"
        }
        self.client = httpx.AsyncClient(headers=self.headers, timeout=settings.REQUEST_TIMEOUT_SECONDS)
        
    async def get_matches(self) -> Dict[str, Any]:
        """Fetch the upcoming matches data."""
        url = f"{self.base_url}/{settings.LEAGUE_ID}/matches"
        response = await self.client.get(url)
        response.raise_for_status()
        return response.json()

    async def get_results(self, skip: int = 0, take: int = 10) -> Dict[str, Any]:
        """Fetch the completed matches results."""
        url = f"{self.base_url}/{settings.LEAGUE_ID}/results"
        params = {"skip": skip, "take": take}
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()
        
    async def get_ranking(self) -> Dict[str, Any]:
        """Fetch the league ranking standings."""
        url = f"{self.base_url}/{settings.LEAGUE_ID}/ranking"
        response = await self.client.get(url)
        response.raise_for_status()
        return response.json()

    async def close(self):
        """Close the async client session."""
        await self.client.aclose()
