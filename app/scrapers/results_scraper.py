from app.clients.http_client import VirtualLeagueClient
from app.models.database_models import RawPayload
from app.utils.disk_check import save_raw_json
import json
import logging
from pathlib import Path
from datetime import datetime
from app.utils.hashing import calculate_hash
from typing import Optional
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

class ResultsScraper:
    def __init__(self, raw_data_dir: Path):
        self.client = VirtualLeagueClient()
        self.raw_data_dir = raw_data_dir / "results"
        self.raw_data_dir.mkdir(parents=True, exist_ok=True)
        
    async def collect(self, skip: int = 0, take: int = 50, db_session: Optional[Session] = None) -> dict:
        """Fetch the results data and save raw payload."""
        logger.info("Fetching results from API...")
        data = await self.client.get_results(skip=skip, take=take)
        
        # Calculate hash and save raw payload
        raw_str = json.dumps(data)
        payload_hash = calculate_hash(raw_str)
        
        now = datetime.utcnow()
        date_path = self.raw_data_dir / str(now.year) / f"{now.month:02d}" / f"{now.day:02d}"
        
        filename = f"{now.strftime('%Y%m%d_%H%M%S')}_{payload_hash[:8]}.json"
        filepath = save_raw_json(date_path, filename, raw_str)
        if filepath:
            logger.info(f"Saved raw results payload to {filepath}")
        
        # Write to raw_payloads DB table if session provided
        if db_session:
            raw_payload = RawPayload(
                source_type="results",
                endpoint=f"/instantleagues/{self._get_league_id()}/results?skip={skip}&take={take}",
                payload_hash=payload_hash,
                storage_path=str(filepath) if filepath else None,
                http_status=200
            )
            db_session.add(raw_payload)
            logger.debug("Recorded raw results payload in DB")
        
        return data

    def _get_league_id(self) -> int:
        from app.config.settings import settings
        return settings.LEAGUE_ID

    async def close(self):
        await self.client.close()
