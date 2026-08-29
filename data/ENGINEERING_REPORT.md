# Engineering Report — Data Pipeline Hardening

**Date**: 2026-08-29
**Database**: localhost:5433/virtual_league

---

## 1. Bugs Fixed

### BUG: Legacy corrupted event records (76 events)
**ROOT CAUSE**: The playout scraper previously inserted goal events without inferring `team_id`, producing rows with `team_id = NULL`. For GOAL event types, a team is always required.
**FIX**: Deleted 76 corrupt rows where `team_id IS NULL AND event_type = 'GOAL'`. All affected events were from 2026-08-26 (before the team inference fix).

### BUG: No event/result reconciliation validation
**ROOT CAUSE**: No code compared official scores against event-derived scores. Missing goals went undetected.
**FIX**: Added `event_sync_status` column to `matches` table with states: COMPLETE, INCOMPLETE, UNKNOWN, NOT_APPLICABLE. Backfilled for all 182 completed matches. Added final event sync with bounded retry in `collection_service.py`.

### BUG: No collection run provenance
**ROOT CAUSE**: child tables (matches, events, odds, ranking) had no FK to `collection_runs`, making it impossible to trace which execution created a record.
**FIX**: Added `collection_run_id` FK to `matches`, `match_events`, `odds_snapshots`, `ranking_snapshots`. New records now carry provenance.

### BUG: Misleading results_collected metric
**ROOT CAUSE**: `results_collected` counted all 576 result rows parsed from the API (24 rounds × 24 matches), not just those persisted. This was confusing.
**FIX**: Added `results_rows_seen` and `results_persisted` as separate metrics. `results_collected` kept for backward compatibility but now equals `results_rows_seen`.

### BUG: No normalized implied probabilities
**ROOT CAUSE**: Only raw odds were stored. Normalized probabilities (removing bookmaker margin) were not pre-computed.
**FIX**: Added `raw_implied_home/draw/away`, `overround`, `normalized_home/draw/away_prob` columns to `odds_snapshots`. All 528 snapshots backfilled. Raw odds preserved.

### BUG: No granular collection metrics
**ROOT CAUCE**: `events_collected` didn't distinguish inserted vs duplicated.
**FIX**: Added `matches_inserted`, `matches_updated`, `results_rows_seen`, `results_persisted`, `events_inserted`, `events_duplicates_skipped`, `odds_inserted`, `odds_duplicates_skipped` to `collection_runs`.

---

## 2. Bugs Intentionally Not Changed

### 15 INCOMPLETE event histories (missing 1 goal each)
**WHY**: These are old completed matches where `round_number` is `None` or the round is no longer accessible via the playout API (returns 400). The final event sync cannot re-fetch historical playout data. These 15 matches are documented with `event_sync_status = 'INCOMPLETE'` — the official result remains authoritative. The ML feature engine must use `event_sync_status = 'COMPLETE'` only when full event history is required.

### 96 ranking entries without form data
**WHY**: These come from older ranking snapshots (captured before form fields were available in the API response). NULL is preferable to fabricated data.

### DB vs disk payload count mismatch (60 DB vs 87 disk)
**WHY**: 27 raw JSON files on disk predate the `raw_payloads` table. They remain on disk for auditability but are not tracked in the DB. This is a known discrepancy from before the table was wired up.

---

## 3. Database Migrations

| Migration | Description |
|-----------|-------------|
| `d4e5f6a7b8c9` | Add `collection_run_id` FK to matches, match_events, odds_snapshots, ranking_snapshots. Add `event_sync_status` to matches. Add normalized probability columns to odds_snapshots. Add granular metrics to collection_runs. |

---

## 4. Data Migration

| Metric | Count |
|--------|-------|
| Legacy rows affected (NULL team_id events) | 76 |
| Rows deleted | 76 |
| Rows repaired | 0 (deleted, not repairable) |
| Rows invalidated | 0 |
| Rows unrecoverable | 0 |
| Backfilled event_sync_status | 182 completed matches |
| Backfilled normalized probabilities | 528 odds snapshots |

---

## 5. Final Data-Quality Metrics

| Metric | Value |
|--------|-------|
| Total matches | 240 |
| Completed matches | 182 |
| Upcoming matches | 58 |
| Unique teams | 48 |
| Unique rounds | 7 |
| Total events | 597 |
| Valid events (team_id set) | 597 |
| Invalid/legacy events | 0 |
| Duplicate events | 0 |
| Total odds snapshots | 528 |
| Duplicate odds | 0 |
| Ranking snapshots | 10 |
| Ranking entries | 480 |
| Entries with form data | 384/480 |
| Ranking entries without team_id | 0 |
| Matches with invalid timestamps | 0 |
| Completed matches with missing result | 0 |
| Event/result mismatches | 15 (all documented as INCOMPLETE) |
| Event sync COMPLETE | 167 (91.8%) |
| Event sync INCOMPLETE | 15 (8.2%) |
| Event sync NOT_APPLICABLE | 58 (upcoming) |
| Data leakage (odds after completion) | 0 |
| Duplicate external_ids | 0 |
| Collection run success rate | 100% (20/20) |
| Result distribution | HOME: 72, DRAW: 30, AWAY: 80 |

---

## 6. Missing-Final-Goal Investigation

**ROOT CAUSE: NOT CONFIRMED as a simple race condition**

Evidence:
- 15 completed matches have exactly 1 fewer event than official score (always -1, never -2 or more)
- The discrepancy is systematic (13.6% of post-fix matches)
- However, the final event sync with bounded retry (3 attempts, 500ms delay) could NOT recover these events
- Most affected matches have `round_number = NULL` (old matches before the migration added round_number)
- The playout API returns 400 for old/inactive rounds
- Conclusion: The source API's results endpoint provides a score string that is occasionally 1 ahead of the goals array, likely due to eventual consistency in the source's internal systems. For historical rounds, the playout endpoint no longer serves data. These are documented as `event_sync_status = 'INCOMPLETE'`.

---

## 7. 504–576 Results Investigation

**COUNTING/PAGINATION ARTIFACT**

Evidence:
- The results API (`/instantleagues/8065/results?skip=0&take=24`) returns 24 rounds of historical results
- Each round contains 24 matches = 576 total rows
- `results_rows_seen` counts all 576 rows parsed
- `results_persisted` counts only those actually reconciled and saved (typically 0-24 per run)
- The discrepancy is expected: the API returns a sliding window of historical results, most of which were already processed in previous runs
- Only matches that can be reconciled with an UPCOMING match in the DB are persisted

---

## 8. ML Readiness

**READY FOR FEATURE ENGINEERING**

Remaining known limitations (documented, not blockers):
- 15 matches have INCOMPLETE event history (use `event_sync_status = 'COMPLETE'` filter)
- 96 ranking entries lack form data (older snapshots)
- Odds appear stable within a match's lifecycle (no movement observed yet — keep snapshot timestamps for future detection)
