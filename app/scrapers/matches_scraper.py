from app.clients.http_client import VirtualLeagueClient
from app.models.schemas import MatchesResponseModel
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

class MatchesScraper:
    def __init__(self, raw_data_dir: Path):
        self.client = VirtualLeagueClient()
        self.raw_data_dir = raw_data_dir / "matches"
        self.raw_data_dir.mkdir(parents=True, exist_ok=True)
        
    async def collect(self, db_session: Optional[Session] = None) -> MatchesResponseModel:
        """Fetch the matches data, save raw payload, and return parsed model."""
        logger.info("Fetching matches from API...")
        data = await self.client.get_matches()
        
        # Calculate hash and save raw payload
        raw_str = json.dumps(data)
        payload_hash = calculate_hash(raw_str)
        
        now = datetime.utcnow()
        date_path = self.raw_data_dir / str(now.year) / f"{now.month:02d}" / f"{now.day:02d}"
        
        filename = f"{now.strftime('%Y%m%d_%H%M%S')}_{payload_hash[:8]}.json"
        filepath = save_raw_json(date_path, filename, raw_str)
        if filepath:
            logger.info(f"Saved raw matches payload to {filepath}")
        
        # Write to raw_payloads DB table if session provided
        if db_session:
            raw_payload = RawPayload(
                source_type="matches",
                endpoint=f"/instantleagues/{self._get_league_id()}/matches",
                payload_hash=payload_hash,
                storage_path=str(filepath) if filepath else None,
                http_status=200
            )
            db_session.add(raw_payload)
            logger.debug("Recorded raw matches payload in DB")
        
        # Validate and return Pydantic model
        return MatchesResponseModel(**data)

    def _get_league_id(self) -> int:
        from app.config.settings import settings
        return settings.LEAGUE_ID

    async def close(self):
        await self.client.close()
