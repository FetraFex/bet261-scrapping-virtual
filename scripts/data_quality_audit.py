#!/usr/bin/env python
"""
Virtual League Collector — Comprehensive Post-Fix Data Quality Audit
=====================================================================
Generates a detailed report covering every dimension of data quality:
  1. Table row counts and coverage
  2. Orphan / referential-integrity checks
  3. Deduplication health
  4. Odds sanity (implied probabilities, overround)
  5. Score integrity (half-time vs full-time consistency)
  6. Goal-event consistency with scores
  7. Temporal integrity (no future-feature leakage)
  8. Ranking snapshot health
  9. Raw-payload coverage
 10. Collection-run reliability
 11. Per-round breakdown
 12. Team coverage analysis
 13. Odds change frequency analysis
"""

import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import sessionmaker

# ---------------------------------------------------------------------------
# Bootstrap path so we can import app modules regardless of cwd
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.config.settings import settings
from app.models.database_models import (
    Match, OddsSnapshot, MatchEvent, RankingSnapshot, RankingEntry,
    Team, League, CollectionRun, RawPayload, ScraperError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
SEP = "=" * 70
SUB = "-" * 70
_line = lambda: print(SUB)
_header = lambda title: (print(), print(SEP), print(f"  {title}"), print(SEP))
_sub = lambda title: (print(), print(f"  {title}"), print(SUB))


def _pct(a, b):
    return f"{a/b*100:.1f}%" if b else "N/A"


def _query(conn, sql, params=None):
    return conn.execute(text(sql), params or {}).fetchall()


def _scalar(conn, sql, params=None):
    return conn.execute(text(sql), params or {}).scalar()


# ---------------------------------------------------------------------------
# Audit sections
# ---------------------------------------------------------------------------

def section_1_table_counts(conn):
    _header("1. TABLE ROW COUNTS")
    tables = [
        ("leagues", "league"),
        ("teams", "team"),
        ("matches", "match"),
        ("odds_snapshots", "odds_snapshot"),
        ("match_events", "match_event"),
        ("ranking_snapshots", "ranking_snapshot"),
        ("ranking_entries", "ranking_entry"),
        ("raw_payloads", "raw_payload"),
        ("collection_runs", "collection_run"),
        ("scraper_errors", "scraper_error"),
    ]
    print(f"  {'Table':<25} {'Rows':>10}")
    print(f"  {'-'*25} {'-'*10}")
    for tbl, _ in tables:
        cnt = _scalar(conn, f"SELECT COUNT(*) FROM {tbl}")
        print(f"  {tbl:<25} {cnt:>10}")


def section_2_match_status(conn):
    _header("2. MATCH STATUS BREAKDOWN")
    rows = _query(conn, """
        SELECT status, COUNT(*) as cnt,
               MIN(scheduled_at) as earliest,
               MAX(scheduled_at) as latest
        FROM matches GROUP BY status ORDER BY status
    """)
    print(f"  {'Status':<15} {'Count':>7}  {'Earliest':<22} {'Latest':<22}")
    print(f"  {'-'*15} {'-'*7}  {'-'*22} {'-'*22}")
    for r in rows:
        print(f"  {r[0]:<15} {r[1]:>7}  {str(r[2])[:22]:<22} {str(r[3])[:22]:<22}")


def section_3_referential_integrity(conn):
    _header("3. REFERENTIAL INTEGRITY CHECKS")
    checks = [
        ("Matches with no home_team_id", """
            SELECT COUNT(*) FROM matches WHERE home_team_id IS NULL
        """),
        ("Matches with no away_team_id", """
            SELECT COUNT(*) FROM matches WHERE away_team_id IS NULL
        """),
        ("Matches with no league_id", """
            SELECT COUNT(*) FROM matches WHERE league_id IS NULL
        """),
        ("Matches with no external_id (or 0)", """
            SELECT COUNT(*) FROM matches
            WHERE external_id IS NULL OR external_id = 0
        """),
        ("Matches with no scheduled_at", """
            SELECT COUNT(*) FROM matches WHERE scheduled_at IS NULL
        """),
        ("Odds snapshots with no match_id", """
            SELECT COUNT(*) FROM odds_snapshots WHERE match_id IS NULL
        """),
        ("Match events with no match_id", """
            SELECT COUNT(*) FROM match_events WHERE match_id IS NULL
        """),
        ("Ranking entries with no snapshot_id", """
            SELECT COUNT(*) FROM ranking_entries WHERE snapshot_id IS NULL
        """),
        ("Ranking entries with no team_id", """
            SELECT COUNT(*) FROM ranking_entries WHERE team_id IS NULL
        """),
    ]
    all_ok = True
    for label, sql in checks:
        cnt = _scalar(conn, sql)
        status = "[OK]" if cnt == 0 else "[WARN]"
        if cnt > 0:
            all_ok = False
        print(f"  {status} {label}: {cnt}")
    if all_ok:
        print()
        print("  ALL referential integrity checks passed.")


def section_4_deduplication(conn):
    _header("4. DEDUPLICATION HEALTH")

    # Duplicate external_ids
    dupes = _query(conn, """
        SELECT external_id, COUNT(*) as cnt
        FROM matches
        WHERE external_id IS NOT NULL AND external_id != 0
        GROUP BY external_id HAVING COUNT(*) > 1
    """)
    if dupes:
        print(f"  [WARN] {len(dupes)} duplicate external_id(s) found:")
        for d in dupes[:10]:
            print(f"          external_id={d[0]}  count={d[1]}")
    else:
        print("  [OK] No duplicate external_ids.")

    # Duplicate odds snapshots (same match, same captured_at)
    dup_odds = _scalar(conn, """
        SELECT COUNT(*) FROM (
            SELECT match_id, captured_at, COUNT(*) as cnt
            FROM odds_snapshots
            GROUP BY match_id, captured_at HAVING COUNT(*) > 1
        ) sub
    """)
    print(f"  {'[OK]' if dup_odds == 0 else '[WARN]'} Duplicate odds (same match+time): {dup_odds}")

    # Duplicate ranking entries per snapshot
    dup_rank = _scalar(conn, """
        SELECT COUNT(*) FROM (
            SELECT snapshot_id, team_id, COUNT(*) as cnt
            FROM ranking_entries
            GROUP BY snapshot_id, team_id HAVING COUNT(*) > 1
        ) sub
    """)
    print(f"  {'[OK]' if dup_rank == 0 else '[WARN]'} Duplicate ranking entries per snapshot: {dup_rank}")

    # Duplicate match events per match+minute
    dup_events = _scalar(conn, """
        SELECT COUNT(*) FROM (
            SELECT match_id, minute, COUNT(*) as cnt
            FROM match_events
            GROUP BY match_id, minute HAVING COUNT(*) > 1
        ) sub
    """)
    print(f"  {'[OK]' if dup_events == 0 else '[WARN]'} Duplicate goal events (same match+minute): {dup_events}")


def section_5_odds_sanity(conn):
    _header("5. ODDS SANITY CHECKS")

    # Odds range
    stats = _query(conn, """
        SELECT
            MIN(home_odds) as min_h, MAX(home_odds) as max_h, AVG(home_odds) as avg_h,
            MIN(draw_odds) as min_d, MAX(draw_odds) as max_d, AVG(draw_odds) as avg_d,
            MIN(away_odds) as min_a, MAX(away_odds) as max_a, AVG(away_odds) as avg_a
        FROM odds_snapshots
    """)
    if stats:
        s = stats[0]
        print(f"  Home odds: min={s[0]:.2f}  max={s[1]:.2f}  avg={s[2]:.2f}")
        print(f"  Draw odds: min={s[3]:.2f}  max={s[4]:.2f}  avg={s[5]:.2f}")
        print(f"  Away odds: min={s[6]:.2f}  max={s[7]:.2f}  avg={s[8]:.2f}")

    # Check for zero or negative odds
    bad_odds = _scalar(conn, """
        SELECT COUNT(*) FROM odds_snapshots
        WHERE home_odds <= 0 OR draw_odds <= 0 OR away_odds <= 0
    """)
    print(f"  {'[OK]' if bad_odds == 0 else '[WARN]'} Zero/negative odds: {bad_odds}")

    # Overround (implied probability sum)
    orr = _query(conn, """
        SELECT match_id,
               (1.0/home_odds + 1.0/draw_odds + 1.0/away_odds) as overround
        FROM odds_snapshots
        WHERE home_odds > 0 AND draw_odds > 0 AND away_odds > 0
    """)
    if orr:
        overrounds = [float(r[1]) for r in orr]
        print(f"  Overround (implied prob sum):")
        print(f"    min={min(overrounds):.4f}  max={max(overrounds):.4f}  "
              f"avg={sum(overrounds)/len(overrounds):.4f}  count={len(overrounds)}")
        # Overround < 1.0 means odds are wrong (house edge is negative)
        bad_orr = sum(1 for o in overrounds if o < 1.0)
        print(f"    [OK] {bad_orr} snapshot(s) with overround < 1.0 (impossible)" if bad_orr > 0 else
              f"    [OK] No overround anomalies (< 1.0)")

    # Odds range reasonableness (1X2 odds typically 1.01 - 100)
    extreme = _scalar(conn, """
        SELECT COUNT(*) FROM odds_snapshots
        WHERE home_odds > 100 OR draw_odds > 100 OR away_odds > 100
           OR home_odds < 1.01 OR draw_odds < 1.01 OR away_odds < 1.01
    """)
    print(f"  {'[OK]' if extreme == 0 else '[WARN]'} Extreme odds (>100 or <1.01): {extreme}")


def section_6_score_integrity(conn):
    _header("6. SCORE INTEGRITY CHECKS")

    # Matches with scores but status UPCOMING
    upcoming_with_scores = _scalar(conn, """
        SELECT COUNT(*) FROM matches
        WHERE status = 'UPCOMING'
        AND (home_score IS NOT NULL OR away_score IS NOT NULL)
    """)
    print(f"  {'[OK]' if upcoming_with_scores == 0 else '[WARN]'} UPCOMING matches with scores: {upcoming_with_scores}")

    # COMPLETED matches without scores
    completed_no_scores = _scalar(conn, """
        SELECT COUNT(*) FROM matches
        WHERE status = 'COMPLETED'
        AND (home_score IS NULL OR away_score IS NULL)
    """)
    print(f"  {'[OK]' if completed_no_scores == 0 else '[WARN]'} COMPLETED matches without scores: {completed_no_scores}")

    # Half-time vs full-time consistency
    ht_ft_bad = _scalar(conn, """
        SELECT COUNT(*) FROM matches
        WHERE half_home_score IS NOT NULL AND half_away_score IS NOT NULL
        AND home_score IS NOT NULL AND away_score IS NOT NULL
        AND (half_home_score > home_score OR half_away_score > away_score)
    """)
    print(f"  {'[OK]' if ht_ft_bad == 0 else '[WARN]'} HT scores exceeding FT scores: {ht_ft_bad}")

    # COMPLETED matches with 0:0 score
    draws_00 = _scalar(conn, """
        SELECT COUNT(*) FROM matches
        WHERE status = 'COMPLETED' AND home_score = 0 AND away_score = 0
    """)
    print(f"  [INFO] 0:0 draws: {draws_00}")

    # Score distribution
    score_dist = _query(conn, """
        SELECT home_score, away_score, COUNT(*) as cnt
        FROM matches
        WHERE status = 'COMPLETED'
        AND home_score IS NOT NULL
        GROUP BY home_score, away_score
        ORDER BY cnt DESC
        LIMIT 10
    """)
    if score_dist:
        print(f"  Top score lines:")
        for r in score_dist:
            print(f"    {r[0]}:{r[1]:>2}  ({r[2]} matches)")


def section_7_goal_event_consistency(conn):
    _header("7. GOAL EVENT vs SCORE CONSISTENCY")

    # Total goal events
    total_events = _scalar(conn, "SELECT COUNT(*) FROM match_events")
    print(f"  Total goal events: {total_events}")

    # Completed matches with no goals but score > 0
    no_goals_but_scored = _query(conn, """
        SELECT m.id, m.home_score, m.away_score,
               (SELECT COUNT(*) FROM match_events me WHERE me.match_id = m.id) as event_cnt
        FROM matches m
        WHERE m.status = 'COMPLETED'
        AND m.home_score IS NOT NULL AND m.away_score IS NOT NULL
        AND (m.home_score + m.away_score) > 0
        AND NOT EXISTS (SELECT 1 FROM match_events me WHERE me.match_id = m.id)
        LIMIT 10
    """)
    if no_goals_but_scored:
        print(f"  [WARN] Completed matches with goals in score but no events: {len(no_goals_but_scored)}")
        for r in no_goals_but_scored[:5]:
            print(f"          match {r[0]}: {r[1]}-{r[2]} (0 events)")
    else:
        print("  [OK] All completed matches with goals have goal events.")

    # Goal events for non-completed matches
    events_no_completed = _scalar(conn, """
        SELECT COUNT(DISTINCT me.match_id) FROM match_events me
        JOIN matches m ON me.match_id = m.id
        WHERE m.status != 'COMPLETED'
    """)
    print(f"  [INFO] Goal events on non-COMPLETED matches: {events_no_completed} match(es)")


def section_8_temporal_integrity(conn):
    _header("8. TEMPORAL INTEGRITY (DATA LEAKAGE)")

    # Odds captured AFTER match completion
    leakage = _scalar(conn, """
        SELECT COUNT(*) FROM matches m
        JOIN odds_snapshots o ON m.id = o.match_id
        WHERE m.completed_at IS NOT NULL
        AND o.captured_at > m.completed_at
    """)
    print(f"  {'[OK]' if leakage == 0 else '[LEAKAGE!]'} Odds snapshots after match completion: {leakage}")

    # Odds captured at exact same time as completion (suspicious)
    exact_timing = _scalar(conn, """
        SELECT COUNT(*) FROM matches m
        JOIN odds_snapshots o ON m.id = o.match_id
        WHERE m.completed_at IS NOT NULL
        AND o.captured_at = m.completed_at
    """)
    print(f"  {'[OK]' if exact_timing == 0 else '[WARN]'} Odds snapshots at exact completion time: {exact_timing}")

    # Match scheduled_at in the future (UPCOMING)
    future_matches = _scalar(conn, """
        SELECT COUNT(*) FROM matches
        WHERE status = 'UPCOMING'
        AND scheduled_at < NOW()
    """)
    print(f"  [INFO] UPCOMING matches with scheduled_at in the past: {future_matches}")

    # Match completed_at before scheduled_at
    completed_early = _scalar(conn, """
        SELECT COUNT(*) FROM matches
        WHERE completed_at IS NOT NULL AND scheduled_at IS NOT NULL
        AND completed_at < scheduled_at
    """)
    print(f"  {'[OK]' if completed_early == 0 else '[WARN]'} Completed before scheduled: {completed_early}")


def section_9_ranking_health(conn):
    _header("9. RANKING SNAPSHOT HEALTH")

    snapshots = _scalar(conn, "SELECT COUNT(*) FROM ranking_snapshots")
    entries = _scalar(conn, "SELECT COUNT(*) FROM ranking_entries")
    print(f"  Snapshots: {snapshots}")
    print(f"  Entries:   {entries}")
    if snapshots > 0:
        avg_entries = entries / snapshots
        print(f"  Avg entries/snapshot: {avg_entries:.1f}")

    # Teams with no ranking entry
    teams_no_rank = _scalar(conn, """
        SELECT COUNT(*) FROM teams t
        WHERE NOT EXISTS (
            SELECT 1 FROM ranking_entries re WHERE re.team_id = t.id
        )
    """)
    print(f"  [INFO] Teams without any ranking entry: {teams_no_rank}")

    # Ranking entries with no form data
    no_form = _scalar(conn, """
        SELECT COUNT(*) FROM ranking_entries
        WHERE (form_position_1 IS NULL OR form_position_1 = '')
        AND (form_position_2 IS NULL OR form_position_2 = '')
    """)
    print(f"  {'[OK]' if no_form == 0 else '[INFO]'} Ranking entries without form data: {no_form}")

    # Snapshot deduplication check
    dup_snapshots = _scalar(conn, """
        SELECT COUNT(*) FROM (
            SELECT source_hash, COUNT(*) as cnt
            FROM ranking_snapshots
            GROUP BY source_hash HAVING COUNT(*) > 1
        ) sub
    """)
    print(f"  {'[OK]' if dup_snapshots == 0 else '[INFO]'} Duplicate ranking snapshots (same hash): {dup_snapshots}")


def section_10_raw_payload_coverage(conn):
    _header("10. RAW PAYLOAD COVERAGE")

    runs = _scalar(conn, "SELECT COUNT(*) FROM collection_runs")
    payloads = _scalar(conn, "SELECT COUNT(*) FROM raw_payloads")
    print(f"  Collection runs: {runs}")
    print(f"  Raw payloads:    {payloads}")

    if runs > 0:
        avg = payloads / runs
        print(f"  Avg payloads/run: {avg:.1f}")

    # Payload type distribution
    types = _query(conn, """
        SELECT source_type, COUNT(*) as cnt
        FROM raw_payloads GROUP BY source_type ORDER BY cnt DESC
    """)
    if types:
        print(f"  Payload types:")
        for r in types:
            print(f"    {r[0]:<20} {r[1]:>5}")

    # Verify raw files exist on disk
    raw_dir = settings.RAW_DATA_DIR
    if raw_dir.exists():
        json_files = list(raw_dir.rglob("*.json"))
        print(f"  Raw JSON files on disk: {len(json_files)}")
        # Check disk vs DB consistency
        if payloads != len(json_files):
            print(f"  [WARN] DB payloads ({payloads}) != disk files ({len(json_files)})")
        else:
            print(f"  [OK] DB payloads match disk files.")
    else:
        print(f"  [WARN] Raw data directory not found: {raw_dir}")


def section_11_collection_reliability(conn):
    _header("11. COLLECTION RUN RELIABILITY")

    runs = _query(conn, """
        SELECT id, started_at, completed_at, status, matches_collected,
               results_collected, goals_collected, ranking_snapshots, error_message
        FROM collection_runs ORDER BY started_at DESC
    """)
    total = len(runs)
    completed = sum(1 for r in runs if r[3] == "COMPLETED")
    failed = sum(1 for r in runs if r[3] == "FAILED")
    running = sum(1 for r in runs if r[3] == "RUNNING")
    print(f"  Total runs:   {total}")
    print(f"  Completed:    {completed} ({_pct(completed, total)})")
    print(f"  Failed:       {failed} ({_pct(failed, total)})")
    print(f"  Running:      {running}")
    if total > 0:
        print(f"  Success rate: {_pct(completed, total)}")

    # Run durations
    durations = []
    for r in runs:
        if r[1] and r[2]:
            dur = (r[2] - r[1]).total_seconds()
            durations.append(dur)
    if durations:
        print(f"  Run duration: min={min(durations):.1f}s  max={max(durations):.1f}s  "
              f"avg={sum(durations)/len(durations):.1f}s")

    # Scraper errors
    errors = _query(conn, """
        SELECT source_type, error_type, COUNT(*) as cnt
        FROM scraper_errors GROUP BY source_type, error_type ORDER BY cnt DESC
    """)
    if errors:
        print(f"  Scraper errors:")
        for r in errors:
            print(f"    {r[0]:<20} {r[1]:<20} {r[2]:>5}")
    else:
        print(f"  No scraper errors recorded.")

    # Recent runs table
    if runs:
        print()
        print(f"  {'ID':>4} {'Started':<22} {'Status':<12} {'Matches':>8} {'Results':>8} {'Goals':>7}")
        print(f"  {'-'*4} {'-'*22} {'-'*12} {'-'*8} {'-'*8} {'-'*7}")
        for r in runs[:10]:
            started = str(r[1])[:19] if r[1] else "N/A"
            print(f"  {r[0]:>4} {started:<22} {(r[3] or 'N/A'):<12} {r[4] or 0:>8} {r[5] or 0:>8} {r[6] or 0:>7}")


def section_12_per_round_breakdown(conn):
    _header("12. PER-ROUND BREAKDOWN")

    rounds = _query(conn, """
        SELECT round_number,
               COUNT(*) as match_count,
               SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed,
               SUM(CASE WHEN status = 'UPCOMING' THEN 1 ELSE 0 END) as upcoming,
               MIN(scheduled_at) as round_start
        FROM matches
        WHERE round_number IS NOT NULL
        GROUP BY round_number
        ORDER BY round_number
    """)
    if rounds:
        print(f"  {'Round':>6} {'Matches':>8} {'Done':>6} {'Pending':>8} {'Round Start':<22}")
        print(f"  {'-'*6} {'-'*8} {'-'*6} {'-'*8} {'-'*22}")
        for r in rounds:
            rs = str(r[4])[:19] if r[4] else "N/A"
            print(f"  {r[0]:>6} {r[1]:>8} {r[2] or 0:>6} {r[3] or 0:>8} {rs:<22}")
        print(f"\n  Total rounds: {len(rounds)}")


def section_13_team_coverage(conn):
    _header("13. TEAM COVERAGE ANALYSIS")

    teams = _query(conn, """
        SELECT t.canonical_name,
               COUNT(DISTINCT m.id) as match_count,
               SUM(CASE WHEN m.status = 'COMPLETED' THEN 1 ELSE 0 END) as completed
        FROM teams t
        LEFT JOIN matches m ON (m.home_team_id = t.id OR m.away_team_id = t.id)
        GROUP BY t.id, t.canonical_name
        ORDER BY match_count DESC
    """)
    if teams:
        print(f"  Total teams: {len(teams)}")
        print(f"  {'Team':<25} {'Matches':>8} {'Completed':>10}")
        print(f"  {'-'*25} {'-'*8} {'-'*10}")
        for r in teams:
            print(f"  {(r[0] or 'N/A'):<25} {r[1] or 0:>8} {r[2] or 0:>10}")

        # Check for teams with no matches
        zero_match_teams = sum(1 for t in teams if (t[1] or 0) == 0)
        print(f"\n  Teams with 0 matches: {zero_match_teams}")


def section_14_odds_change_frequency(conn):
    _header("14. ODDS CHANGE FREQUENCY")

    # Matches with multiple odds snapshots
    odds_counts = _query(conn, """
        SELECT snapshot_count, COUNT(*) as match_cnt
        FROM (
            SELECT match_id, COUNT(*) as snapshot_count
            FROM odds_snapshots GROUP BY match_id
        ) sub
        GROUP BY snapshot_count ORDER BY snapshot_count
    """)
    if odds_counts:
        print(f"  {'Snapshots/Match':>16} {'Matches':>10}")
        print(f"  {'-'*16} {'-'*10}")
        for r in odds_counts:
            print(f"  {r[0]:>16} {r[1]:>10}")

    total_matches_with_odds = _scalar(conn, "SELECT COUNT(DISTINCT match_id) FROM odds_snapshots")
    total_snapshots = _scalar(conn, "SELECT COUNT(*) FROM odds_snapshots")
    print(f"\n  Total matches with odds: {total_matches_with_odds}")
    print(f"  Total odds snapshots:    {total_snapshots}")
    if total_matches_with_odds > 0:
        print(f"  Avg snapshots/match:     {total_snapshots/total_matches_with_odds:.2f}")


def section_15_summary(conn):
    _header("15. EXECUTIVE SUMMARY")

    matches = _scalar(conn, "SELECT COUNT(*) FROM matches")
    completed = _scalar(conn, "SELECT COUNT(*) FROM matches WHERE status='COMPLETED'")
    upcoming = _scalar(conn, "SELECT COUNT(*) FROM matches WHERE status='UPCOMING'")
    odds = _scalar(conn, "SELECT COUNT(*) FROM odds_snapshots")
    events = _scalar(conn, "SELECT COUNT(*) FROM match_events")
    teams = _scalar(conn, "SELECT COUNT(*) FROM teams")
    rankings = _scalar(conn, "SELECT COUNT(*) FROM ranking_snapshots")
    ranking_entries = _scalar(conn, "SELECT COUNT(*) FROM ranking_entries")
    runs = _scalar(conn, "SELECT COUNT(*) FROM collection_runs")
    run_ok = _scalar(conn, "SELECT COUNT(*) FROM collection_runs WHERE status='COMPLETED'")
    raw = _scalar(conn, "SELECT COUNT(*) FROM raw_payloads")
    errors = _scalar(conn, "SELECT COUNT(*) FROM scraper_errors")

    # Odds coverage
    matches_with_odds = _scalar(conn, """
        SELECT COUNT(DISTINCT m.id) FROM matches m
        JOIN odds_snapshots o ON m.id = o.match_id
    """)
    # Score coverage for completed
    completed_with_scores = _scalar(conn, """
        SELECT COUNT(*) FROM matches WHERE status='COMPLETED'
        AND home_score IS NOT NULL AND away_score IS NOT NULL
    """)

    # Ranking coverage
    teams_with_ranking = _scalar(conn, """
        SELECT COUNT(DISTINCT re.team_id) FROM ranking_entries re
        WHERE re.team_id IS NOT NULL
    """)

    # Temporal leakage
    leakage = _scalar(conn, """
        SELECT COUNT(*) FROM matches m
        JOIN odds_snapshots o ON m.id = o.match_id
        WHERE m.completed_at IS NOT NULL AND o.captured_at > m.completed_at
    """)

    # Duplicate check
    dup_external = _scalar(conn, """
        SELECT COUNT(*) FROM (
            SELECT external_id FROM matches
            WHERE external_id IS NOT NULL AND external_id != 0
            GROUP BY external_id HAVING COUNT(*) > 1
        ) sub
    """)

    print(f"""
  DATABASE HEALTH:
    Matches:           {matches:>6}  ({completed} completed, {upcoming} upcoming)
    Teams:             {teams:>6}
    Odds Snapshots:    {odds:>6}
    Goal Events:       {events:>6}
    Ranking Snapshots: {rankings:>6}
    Ranking Entries:   {ranking_entries:>6}
    Collection Runs:   {runs:>6}  ({run_ok} successful)
    Raw Payloads:      {raw:>6}
    Scraper Errors:    {errors:>6}

  COVERAGE:
    Matches with odds:         {matches_with_odds}/{matches} ({_pct(matches_with_odds, matches)})
    Completed with scores:     {completed_with_scores}/{completed} ({_pct(completed_with_scores, completed)})
    Teams with ranking:        {teams_with_ranking}/{teams} ({_pct(teams_with_ranking, teams)})

  INTEGRITY:
    Data leakage (odds after completion): {leakage}  {'[OK]' if leakage == 0 else '[FAIL]'}
    Duplicate external_ids:              {dup_external}  {'[OK]' if dup_external == 0 else '[FAIL]'}
    Run success rate:                    {_pct(run_ok, runs)}

  OVERALL STATUS:  {'ALL CHECKS PASSED' if (leakage == 0 and dup_external == 0 and run_ok == runs) else 'ISSUES DETECTED — SEE ABOVE'}
""")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    engine = create_engine(settings.DATABASE_URL)

    print()
    print(SEP)
    print("  VIRTUAL LEAGUE COLLECTOR — POST-FIX DATA QUALITY AUDIT")
    print(f"  Generated: {datetime.now(timezone.utc).isoformat()}")
    print(f"  Database:  {settings.DATABASE_URL.split('@')[-1] if '@' in settings.DATABASE_URL else settings.DATABASE_URL}")
    print(SEP)

    with engine.connect() as conn:
        section_1_table_counts(conn)
        section_2_match_status(conn)
        section_3_referential_integrity(conn)
        section_4_deduplication(conn)
        section_5_odds_sanity(conn)
        section_6_score_integrity(conn)
        section_7_goal_event_consistency(conn)
        section_8_temporal_integrity(conn)
        section_9_ranking_health(conn)
        section_10_raw_payload_coverage(conn)
        section_11_collection_reliability(conn)
        section_12_per_round_breakdown(conn)
        section_13_team_coverage(conn)
        section_14_odds_change_frequency(conn)
        section_15_summary(conn)

    print(SEP)
    print("  AUDIT COMPLETE")
    print(SEP)
    print()


if __name__ == "__main__":
    main()
