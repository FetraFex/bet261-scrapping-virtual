from app.clients.http_client import VirtualLeagueClient
import json
import logging
from pathlib import Path
from datetime import datetime
from app.utils.hashing import calculate_hash

logger = logging.getLogger(__name__)

class ResultsScraper:
    def __init__(self, raw_data_dir: Path):
        self.client = VirtualLeagueClient()
        self.raw_data_dir = raw_data_dir / "results"
        self.raw_data_dir.mkdir(parents=True, exist_ok=True)
        
    async def collect(self) -> list:
        """Fetch the results data and save raw payload."""
        logger.info("Fetching results from API...")
        data = await self.client.get_results(skip=0, take=20)
        
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
            
        logger.info(f"Saved raw results payload to {filepath}")
        
        return data

    async def close(self):
        await self.client.close()
