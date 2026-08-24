from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List
import logging

from app.models.database_models import RankingSnapshot, RankingEntry
from app.utils.hashing import calculate_hash

logger = logging.getLogger(__name__)

class RankingRepository:
    def __init__(self, session: Session):
        self.session = session
        
    def save_ranking(self, league_id: int, entries: List[dict], raw_hash: str) -> bool:
        """
        Saves ranking snapshot ONLY if it has changed from the last known state.
        Returns True if a new snapshot was created, False otherwise.
        """
        last_snapshot = self.session.execute(
            select(RankingSnapshot)
            .filter_by(league_id=league_id)
            .order_by(RankingSnapshot.captured_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        
        if last_snapshot and last_snapshot.source_hash == raw_hash:
            return False # No change
            
        snapshot = RankingSnapshot(
            league_id=league_id,
            source_hash=raw_hash
        )
        self.session.add(snapshot)
        self.session.flush()
        
        for e in entries:
            entry = RankingEntry(
                snapshot_id=snapshot.id,
                team_name=e.get("team_name"),
                rank=e.get("rank", 0),
                points=e.get("points", 0),
                form_position_1=e.get("form", [None])[0] if len(e.get("form", [])) > 0 else None,
                form_position_2=e.get("form", [None]*2)[1] if len(e.get("form", [])) > 1 else None,
                form_position_3=e.get("form", [None]*3)[2] if len(e.get("form", [])) > 2 else None,
                form_position_4=e.get("form", [None]*4)[3] if len(e.get("form", [])) > 3 else None,
                form_position_5=e.get("form", [None]*5)[4] if len(e.get("form", [])) > 4 else None,
            )
            self.session.add(entry)
            
        logger.info(f"Saved new ranking snapshot for league {league_id}")
        return True
