# Virtual League Collector — Architecture

## Overview

A production-quality data collection system for virtual football betting research (League ID `8065` — "World Cup / Instant League" on bet261.mg). The system creates trustworthy, chronological, reproducible datasets for statistical analysis, ML backtesting, and prediction research.

**NOT** for placing bets.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         CLI (main.py)                        │
│  collect-once │ run │ status │ export │ validate │ backfill  │
└───────────────┬─────────────────────────────────────────────┘
                │
┌───────────────▼─────────────────────────────────────────────┐
│              Collection Service (collection_service.py)       │
│  Orchestrates collection cycle: matches → results → playout  │
│  → ranking. Tracks runs, errors, and raw payloads.           │
└──────┬──────────────┬──────────────┬────────────────────────┘
       │              │              │
┌──────▼──────┐ ┌─────▼─────┐ ┌─────▼─────┐
│   Scrapers   │ │  Results  │ │  Ranking  │
│  (3 + 1)    │ │ Scraper   │ │  Scraper  │
└──────┬──────┘ └─────┬─────┘ └─────┬─────┘
       │              │              │
┌──────▼──────────────▼──────────────▼─────────────────────────┐
│              HTTP Client (http_client.py)                      │
│  httpx async + tenacity retry (exponential backoff)            │
│  Endpoints: matches, results, ranking, playout                 │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│              API (hg-event-api-prod.sporty-tech.net)          │
│  /instantleagues/8065/{matches,results,ranking}               │
│  /instantleagues/round/{N}/playout                            │
└─────────────────────────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────────────┐
│                    Data Storage                               │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐    │
│  │ PostgreSQL   │  │ Disk (JSON)  │  │ CSV/Parquet      │    │
│  │ (10 tables)  │  │ data/raw/    │  │ data/exports/    │    │
│  └─────────────┘  └──────────────┘  └──────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

---

## Data Flow

### Collection Cycle

1. **Matches**: Fetch upcoming matches → Parse odds → Deduplicate by `external_id` → Save to `matches` + `odds_snapshots`
2. **Results**: Fetch completed matches → Parse score strings → Reconcile with existing matches → Save scores + goals to `match_events`
3. **Playout**: Fetch goal events for current rounds → Save minute-by-minute goal data
4. **Ranking**: Fetch standings → Hash-based dedup → Save snapshot only if changed

### Raw Data Pipeline

```
API Response → Save to disk (data/raw/) → Save reference to raw_payloads table
```

Every API response is preserved both on disk and referenced in the database. This ensures reproducibility and auditability.

---

## Database Schema

### Tables

| Table | Purpose | Key Features |
|-------|---------|--------------|
| `leagues` | League metadata | `external_id` (unique) |
| `teams` | Team registry | Normalized names, league-scoped |
| `matches` | Match records | Dedup by `external_id`, status tracking |
| `odds_snapshots` | Odds history | Only saved when odds change |
| `match_events` | Goal events | Minute-by-minute from playout/results |
| `ranking_snapshots` | Standings state | Hash-based change detection |
| `ranking_entries` | Individual rankings | Form history (last 5 results) |
| `raw_payloads` | Raw file references | SHA-256 hash of payload |
| `collection_runs` | Run tracking | Status, counts, errors |
| `scraper_errors` | Error logging | Per-source error details |

### Key Relationships

```
League ─┬─ Teams
        ├─ Matches ─┬─ OddsSnapshots
        │           └─ MatchEvents
        ├─ RankingSnapshots ─ RankingEntries
        └─ CollectionRuns ─ ScraperErrors
```

---

## API Endpoints

| Data | Endpoint | Method | Auth |
|------|----------|--------|------|
| Matches | `/instantleagues/8065/matches` | GET | None |
| Results | `/instantleagues/8065/results?skip=0&take=50` | GET | None |
| Ranking | `/instantleagues/8065/ranking` | GET | None |
| Playout | `/instantleagues/round/{N}/playout` | GET | None |

### Important API Behaviors

- **Results `id` is always 0**: Cannot use for deduplication. Use team names + round number.
- **Results `entryPointId` is always 0**: League ID not provided in results.
- **Only active round has matches**: Future rounds have empty `matches` arrays.
- **Odds are in `eventBetTypeItems`**: Not in an `odds` field.
- **Half-time scores available**: `halfTimeScore` field in results (e.g., "0:0").

---

## Key Design Decisions

### Deduplication Strategy

1. **Matches**: By `external_id` (stable API-provided ID like `76827355`)
2. **Results**: By team names + round number (since `id` is always 0)
3. **Ranking**: By SHA-256 hash of entire payload (only save if changed)
4. **Odds**: By comparing with latest snapshot (only save if changed)

### Data Integrity Rules

- **RAW DATA > DERIVED DATA**: Always preserve original API responses
- **NO data leakage**: Every ML feature must be from BEFORE the match
- **UTC timestamps**: All times stored in UTC
- **Deterministic normalization**: Team names normalized but not aliased

### Retry & Resilience

- HTTP requests use `tenacity` with exponential backoff
- 3 retries with 1s-10s wait times
- Collection runs tracked with status and error logging
- Graceful shutdown on SIGINT/SIGTERM

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `collect-once` | Single collection cycle |
| `run` | Continuous collection (Ctrl+C to stop) |
| `status` | Show database statistics |
| `export` | Generate CSV/Parquet files |
| `validate` | Check data integrity |
| `backfill` | Fetch historical data |

---

## Testing

Tests are in `tests/` and cover:
- Pydantic schema validation
- Team name normalization
- SHA-256 hashing
- Score string parsing
- Temporal leakage detection
- Match result determination

Run with: `pytest tests/ -v`

---

## File Structure

```
app/
├── config/settings.py          # pydantic-settings, reads .env
├── clients/http_client.py      # httpx async + tenacity retry
├── scrapers/
│   ├── matches_scraper.py      # Matches API
│   ├── results_scraper.py      # Results API
│   ├── ranking_scraper.py      # Ranking API
│   └── playout_scraper.py      # Playout/goal events
├── models/
│   ├── database_models.py      # SQLAlchemy ORM (10 tables)
│   └── schemas.py              # Pydantic validation
├── repositories/
│   ├── matches_repository.py   # Dedup + odds history
│   ├── results_repository.py   # Match reconciliation
│   └── ranking_repository.py   # Hash-based snapshots
├── services/collection_service.py  # Main orchestrator
├── normalization/team_normalizer.py
├── monitoring/logger.py
├── utils/hashing.py
└── main.py                     # CLI entrypoint

migrations/                     # Alembic migrations
tests/                          # pytest tests
data/
├── raw/                        # Raw JSON payloads
└── exports/                    # Generated CSV/Parquet
```
