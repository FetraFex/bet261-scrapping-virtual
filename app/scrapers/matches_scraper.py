from app.clients.http_client import VirtualLeagueClient
from app.models.schemas import MatchesResponseModel
import json
import logging
from pathlib import Path
from datetime import datetime
from app.utils.hashing import calculate_hash

logger = logging.getLogger(__name__)

class MatchesScraper:
    def __init__(self, raw_data_dir: Path):
        self.client = VirtualLeagueClient()
        self.raw_data_dir = raw_data_dir / "matches"
        self.raw_data_dir.mkdir(parents=True, exist_ok=True)
        
    async def collect(self) -> MatchesResponseModel:
        """Fetch the matches data, save raw payload, and return parsed model."""
        logger.info("Fetching matches from API...")
        data = await self.client.get_matches()
        
        # Calculate hash and save raw payload
        raw_str = json.dumps(data)
        payload_hash = calculate_hash(raw_str)
        
        now = datetime.utcnow()
        date_path = self.raw_data_dir / str(now.year) / f"{now.month:02d}" / f"{now.day:02d}"
        date_path.mkdir(parents=True, exist_ok=True)
        
        filename = f"{now.strftime('%Y%m%d_%H%M%S')}_{payload_hash[:8]}.json"
        filepath = date_path / filename
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(raw_str)
            
        logger.info(f"Saved raw matches payload to {filepath}")
        
        # Validate and return Pydantic model
        return MatchesResponseModel(**data)

    async def close(self):
        await self.client.close()
