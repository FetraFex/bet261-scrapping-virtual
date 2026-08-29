from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List, Optional
import logging

from app.models.database_models import RankingSnapshot, RankingEntry, Team
from app.normalization.team_normalizer import normalize_team_name
from app.utils.hashing import calculate_hash

logger = logging.getLogger(__name__)

class RankingRepository:
    def __init__(self, session: Session):
        self.session = session
        
    def save_ranking(self, league_id: int, entries: List[dict], raw_hash: str, collection_run_id: Optional[int] = None) -> bool:
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
            source_hash=raw_hash,
            collection_run_id=collection_run_id
        )
        self.session.add(snapshot)
        self.session.flush()
        
        for e in entries:
            # Form history from API 'history' field (e.g., ["Draw", "Won", "Won", "Won", "Won"])
            form = e.get("form", [])
            entry = RankingEntry(
                snapshot_id=snapshot.id,
                team_name=e.get("team_name"),
                rank=e.get("rank", 0),
                points=e.get("points", 0),
                form_position_1=form[0] if len(form) > 0 else None,
                form_position_2=form[1] if len(form) > 1 else None,
                form_position_3=form[2] if len(form) > 2 else None,
                form_position_4=form[3] if len(form) > 3 else None,
                form_position_5=form[4] if len(form) > 4 else None,
            )
            self.session.add(entry)
        
        # Flush so that new entries are visible to subsequent queries
        # within the same session (e.g., link_ranking_team_ids).
        self.session.flush()
        
        logger.info(f"Saved new ranking snapshot for league {league_id} with {len(entries)} entries")
        return True

    def link_ranking_team_ids(self, league_id: int) -> int:
        """
        Link ranking_entries.team_id by matching team_name to the teams table.
        Returns the number of entries updated.
        """
        # Build team lookup: normalized_name -> team_id
        teams = self.session.execute(
            select(Team).filter(Team.league_id == league_id)
        ).scalars().all()
        team_map = {}
        for team in teams:
            team_map[normalize_team_name(team.source_name)] = team.id
            # Also map the raw source_name (case-insensitive)
            team_map[team.source_name.lower().strip()] = team.id

        # Find all ranking entries with NULL team_id
        entries = self.session.execute(
            select(RankingEntry).filter(RankingEntry.team_id.is_(None))
        ).scalars().all()

        updated = 0
        for entry in entries:
            if not entry.team_name:
                continue
            # Try normalized match first
            normalized = normalize_team_name(entry.team_name)
            team_id = team_map.get(normalized)
            if not team_id:
                # Try lowercase raw match
                team_id = team_map.get(entry.team_name.lower().strip())
            if team_id:
                entry.team_id = team_id
                updated += 1

        if updated > 0:
            logger.info(f"Linked team_id for {updated} ranking entries")
        return updated
