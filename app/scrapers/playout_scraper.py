from app.clients.http_client import VirtualLeagueClient
from app.config.settings import settings
import json
import logging
from pathlib import Path
from datetime import datetime
from app.utils.hashing import calculate_hash
from typing import Optional

logger = logging.getLogger(__name__)

class PlayoutScraper:
    def __init__(self, raw_data_dir: Path):
        self.client = VirtualLeagueClient()
        self.raw_data_dir = raw_data_dir / "playout"
        self.raw_data_dir.mkdir(parents=True, exist_ok=True)
        
    async def collect(self, round_number: int, event_category_id: int = 8065) -> dict:
        """Fetch playout data for a specific round and save raw payload."""
        logger.info(f"Fetching playout data for round {round_number} from API...")
        data = await self.client.get_playout(round_number, event_category_id)
        
        # Calculate hash and save raw payload
        raw_str = json.dumps(data)
        payload_hash = calculate_hash(raw_str)
        
        now = datetime.utcnow()
        date_path = self.raw_data_dir / str(now.year) / f"{now.month:02d}" / f"{now.day:02d}"
        date_path.mkdir(parents=True, exist_ok=True)
        
        filename = f"{now.strftime('%Y%m%d_%H%M%S')}_round{round_number}_{payload_hash[:8]}.json"
        filepath = date_path / filename
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(raw_str)
            
        logger.info(f"Saved raw playout payload to {filepath}")
        
        return data

    async def close(self):
        await self.client.close()
