# Virtual League Collector — Agent Handoff Document

> **Created**: 2026-08-25T02:04 UTC+3  
> **Project Root**: `e:\Kotrana\bet_261_scrapping`  
> **Remote Repo**: `https://github.com/FetraFex/bet261-scrapping-virtual.git`  
> **Branch**: `main`  
> **Last Commit**: `58ab6f2` — "Working end-to-end collection pipeline"

---

## 1. Project Purpose

Build a production-quality data collection system for a **virtual football betting research project** (League ID `8065` — "World Cup / Instant League" on bet261.mg). The goal is to create a **trustworthy, chronological, reproducible dataset** for statistical analysis, ML backtesting, and prediction research. **NOT** for placing bets.

The full specification with all 36 phases is in the original user prompt — it is very detailed. Read it carefully before continuing.

---

## 2. What Has Been Done

### Phase 1 — Project Foundation (Steps 1–4) ✅

| Component | File | Notes |
|-----------|------|-------|
| Config | [settings.py](file:///e:/Kotrana/bet_261_scrapping/app/config/settings.py) | Uses `pydantic-settings`, reads `.env` |
| .env template | [.env.example](file:///e:/Kotrana/bet_261_scrapping/.env.example) | DB on port **5433** (not 5432) |
| DB | PostgreSQL via Docker on **port 5433** | User has local PG on 5432, so we use 5433 |
| Docker | [docker-compose.yml](file:///e:/Kotrana/bet_261_scrapping/docker-compose.yml) | `docker compose up -d` starts the DB |
| ORM | [database_models.py](file:///e:/Kotrana/bet_261_scrapping/app/models/database_models.py) | SQLAlchemy 2.x declarative models |
| Migrations | [migrations/](file:///e:/Kotrana/bet_261_scrapping/migrations/) | Alembic, initial migration `e5b81ebd9bb6` already applied |
| Deps | [pyproject.toml](file:///e:/Kotrana/bet_261_scrapping/pyproject.toml) | `[tool.setuptools.packages.find] include = ["app*"]` |
| venv | `.venv/` | Python 3.14, activated via `.\.venv\Scripts\activate` |

**Important**: The user does NOT have a `.env` file — the app falls back to defaults in `settings.py`. If you need to create one, copy from `.env.example`.

### Phase 2 — Website Discovery (Step 5) ✅

The discovery script ([discover_endpoints.py](file:///e:/Kotrana/bet_261_scrapping/scripts/discover_endpoints.py)) used Playwright to intercept XHR/Fetch requests. The critical finding: **the website uses clean JSON APIs** behind the scenes. No HTML scraping needed.

#### Discovered API Endpoints (base: `https://hg-event-api-prod.sporty-tech.net/api`)

| Data | Endpoint | Method | Auth |
|------|----------|--------|------|
| **Matches** (upcoming + odds) | `/instantleagues/8065/matches` | GET | None |
| **Results** (completed matches) | `/instantleagues/8065/results?skip=0&take=20` | GET | None |
| **Ranking** (standings) | `/instantleagues/8065/ranking` | GET | None |
| **League details** | `/eventcategories/8065/details` | GET | None |
| **Playout** (goal events) | `/instantleagues/round/{N}/playout?eventCategoryId={id}&parentEventCategoryId=8065` | GET | None |

#### Key API Response Structure (Matches)

```json
{
  "rounds": [
    {
      "expectedStart": "2026-08-24T22:16:18Z",
      "roundNumber": 87,
      "matches": [
        {
          "id": 76827355,           // <-- THIS IS THE STABLE EXTERNAL MATCH ID
          "entryPointId": 8065,
          "round": "87",
          "name": "Turkiye vs Senegal",
          "homeTeam": { "name": "Turkiye", "points": 0, ... },
          "awayTeam": { "name": "Senegal", "points": 0, ... },
          "eventBetTypes": [
            {
              "name": "1X2",
              "eventBetTypeItems": [       // <-- NOT "odds", it's "eventBetTypeItems"
                { "shortName": "1", "odds": 1.67 },
                { "shortName": "X", "odds": 3.63 },
                { "shortName": "2", "odds": 5.37 }
              ]
            }
          ]
        }
      ]
    },
    // Rounds 1-9 exist but have NO "matches" key (future rounds)
  ]
}
```

**Critical detail**: Only Round 0 has `matches` populated. Rounds 1-9 are placeholders for future rounds. The Pydantic schema has `matches: List[MatchModel] = []` to handle this.

#### Key API Response Structure (Playout — Goal Events)

The playout endpoint returns minute-by-minute goals:
```json
{
  "matches": [
    {
      "id": 76827355,
      "goals": [
        { "minute": 27, "homeScore": 1.0, "awayScore": 0.0 },
        { "minute": 82, "homeScore": 2.0, "awayScore": 0.0 }
      ]
    }
  ]
}
```

**This is NOT yet being consumed by the collector.** See "What Remains" below.

### Phase 3 — Scrapers (Steps 6–8) ✅

| Scraper | File | What it does |
|---------|------|-------------|
| Matches | [matches_scraper.py](file:///e:/Kotrana/bet_261_scrapping/app/scrapers/matches_scraper.py) | Fetches matches API, saves raw JSON, returns Pydantic model |
| Results | [results_scraper.py](file:///e:/Kotrana/bet_261_scrapping/app/scrapers/results_scraper.py) | Fetches results API, saves raw JSON, returns dict |
| Ranking | [ranking_scraper.py](file:///e:/Kotrana/bet_261_scrapping/app/scrapers/ranking_scraper.py) | Fetches ranking API, saves raw JSON, returns dict |

All scrapers save raw payloads to `data/raw/{type}/YYYY/MM/DD/YYYYMMDD_HHMMSS_{hash}.json`.

### Phase 4 — Raw Data Storage (Step 9) ✅

Raw payloads are saved to disk. **However**, the `raw_payloads` DB table is NOT being populated yet — only the file system storage works. This needs to be wired up.

### Phase 5 — Repositories & Core Logic (Steps 10–12) ✅

| Repository | File | Key Logic |
|------------|------|-----------|
| Matches | [matches_repository.py](file:///e:/Kotrana/bet_261_scrapping/app/repositories/matches_repository.py) | Deduplication by `external_id`, odds change detection |
| Results | [results_repository.py](file:///e:/Kotrana/bet_261_scrapping/app/repositories/results_repository.py) | Match reconciliation by external_id or time window |
| Ranking | [ranking_repository.py](file:///e:/Kotrana/bet_261_scrapping/app/repositories/ranking_repository.py) | Hash-based snapshot change detection |

**Deduplication**: Works via `external_id` (the API provides a stable match ID like `76827355`). If a match with the same `external_id` already exists, it updates `last_seen_at` instead of creating a duplicate.

**Odds History**: Only creates a new `OddsSnapshot` row when odds actually change compared to the latest snapshot for that match.

**Ranking Snapshots**: Only creates a new snapshot when the SHA-256 hash of the ranking data changes.

### Phase 6 — Collection Loop & CLI (Step 13) ✅

| File | Purpose |
|------|---------|
| [collection_service.py](file:///e:/Kotrana/bet_261_scrapping/app/services/collection_service.py) | Orchestrates `collect_once()` and `run_forever()` |
| [main.py](file:///e:/Kotrana/bet_261_scrapping/app/main.py) | CLI: `python -m app.main collect-once|run|status` |

### Phase 7 — Logging (Step 14) ✅

[logger.py](file:///e:/Kotrana/bet_261_scrapping/app/monitoring/logger.py) — basic structured logging to stdout.

### Verified Working

Two successful `collect-once` runs were performed:
- **Run 1**: Created 24 matches (IDs 1-24) + 24 odds snapshots + 1 ranking snapshot
- **Run 2** (30 seconds later): Created 24 NEW matches (IDs 25-48) — the virtual league had rotated to a new round. This confirms both that deduplication works (no duplicates) and that new rounds are correctly detected.

---

## 3. Database Schema

Tables created (migration `e5b81ebd9bb6`):

| Table | Purpose | Key Indexes |
|-------|---------|-------------|
| `leagues` | League metadata | `external_id` (unique) |
| `teams` | Team registry | `external_id`, `league_id + source_name` |
| `matches` | Match records | `external_id`, `league_id`, `scheduled_at`, `home_team_id`, `away_team_id`, `status` |
| `odds_snapshots` | Odds history per match | `match_id`, `captured_at` |
| `match_events` | Goal events | `match_id` |
| `ranking_snapshots` | Ranking state at a point in time | `league_id`, `captured_at` |
| `ranking_entries` | Individual team ranking within a snapshot | `snapshot_id`, `team_id` |
| `raw_payloads` | Reference to raw files | `payload_hash` |

**Connection string**: `postgresql://postgres:postgres@localhost:5433/virtual_league`

---

## 4. What Remains To Be Done

### HIGH PRIORITY — Core functionality gaps

#### 4.1 Results Parsing Is Not Working Properly
The results scraper saves raw data but the **collection_service.py** results parsing (lines ~70-85) uses placeholder field names (`homeScore`, `awayScore`) that may not match the actual API response structure. **You MUST**:
1. Inspect a saved raw results payload from `data/raw/results/`
2. Determine the actual JSON structure for results
3. Fix the parsing in `collection_service.py`
4. The Results API endpoint also supports pagination: `?skip=0&take=N` — consider fetching more than 20

#### 4.2 Playout / Goal Events Not Consumed
The discovery found a **playout endpoint** (`/instantleagues/round/{N}/playout?eventCategoryId={id}&parentEventCategoryId=8065`) that returns minute-by-minute goal data. This is NOT yet integrated. Add:
- A new method to `http_client.py` to fetch playout data
- Logic in `collection_service.py` to call it after matches complete
- Save goals to the `match_events` table

#### 4.3 `raw_payloads` DB Table Not Populated
The scrapers save files to disk but don't write to the `raw_payloads` database table. Wire this up in the scrapers or collection service.

#### 4.4 Halftime Scores
The spec requires halftime scores (`half_home_score`, `half_away_score`). Check if the results or playout API provides them. The playout endpoint's goal data *could* be used to derive halftime scores (goals before minute 45).

### MEDIUM PRIORITY — Remaining specification steps

#### 4.5 Tests (Step 15)
Create `tests/` with pytest fixtures from saved raw payloads in `data/raw/`. Tests should cover:
- Matches parser (Pydantic validation)
- Results parser
- Ranking parser
- Team normalization
- Deduplication (same external_id → no duplicate)
- Odds change detection
- Match reconciliation
- Temporal leakage detection

Save representative API responses as `tests/fixtures/*.json`.

#### 4.6 Exports (Step 16)
Add `export` CLI command that generates:
- `matches.csv`, `odds_snapshots.csv`, `match_events.csv`, `ranking_snapshots.csv`, `ranking_entries.csv`
- Optionally Parquet format
- An integrated `ml_dataset.csv`

#### 4.7 ML Dataset Generation (Step 17)
Create a feature-generation pipeline that reconstructs **only pre-match information**:
- Rank, points, recent form for each team
- Opening/closing odds
- Implied probabilities
- **Critical**: Implement `validate_no_future_features(match_id)` to prevent data leakage

#### 4.8 Collection Runs & Error Tracking Tables
The spec defines `collection_runs` and `scraper_errors` tables. These are in the spec but NOT in `database_models.py`. Add them and track each collection cycle.

#### 4.9 Retry Logic
The spec requires exponential backoff with `tenacity`. Currently there is NO retry logic in the HTTP client. Add it.

#### 4.10 Graceful Shutdown
`run_forever()` should handle `SIGINT`/`SIGTERM` gracefully (currently just catches `KeyboardInterrupt`).

#### 4.11 Status Command
`python -m app.main status` currently just prints "READY". It should query the DB and show actual stats (matches tracked, completed, odds snapshots, etc.).

### LOW PRIORITY — Polish

#### 4.12 Dockerfile
Not yet created. The spec requires one.

#### 4.13 README.md
Currently a one-liner. The spec requires a comprehensive README (19 sections).

#### 4.14 ARCHITECTURE.md
Not yet created.

#### 4.15 `validate` and `backfill` CLI commands
Not implemented yet.

---

## 5. File Tree (Current State)

```
e:\Kotrana\bet_261_scrapping\
├── app/
│   ├── config/
│   │   └── settings.py              # pydantic-settings, reads .env
│   ├── clients/
│   │   └── http_client.py           # httpx async client for 3 API endpoints
│   ├── discovery/                    # (empty — discovery is in scripts/)
│   ├── scrapers/
│   │   ├── matches_scraper.py       # Fetches + saves raw + returns Pydantic model
│   │   ├── results_scraper.py       # Fetches + saves raw + returns dict
│   │   └── ranking_scraper.py       # Fetches + saves raw + returns dict
│   ├── parsers/                     # (empty — parsing is inline in collection_service)
│   ├── models/
│   │   ├── database_models.py       # SQLAlchemy ORM models (8 tables)
│   │   └── schemas.py               # Pydantic validation schemas
│   ├── repositories/
│   │   ├── matches_repository.py    # Dedup + odds history
│   │   ├── results_repository.py    # Match reconciliation
│   │   └── ranking_repository.py    # Hash-based snapshot detection
│   ├── services/
│   │   └── collection_service.py    # Main orchestrator
│   ├── normalization/
│   │   └── team_normalizer.py       # Basic name normalization
│   ├── storage/                     # (empty — raw storage is in scrapers)
│   ├── monitoring/
│   │   └── logger.py                # Structured logging setup
│   ├── utils/
│   │   └── hashing.py               # SHA-256 utility
│   └── main.py                      # CLI entrypoint
├── migrations/
│   ├── versions/
│   │   └── e5b81ebd9bb6_initial_schema.py
│   └── env.py                       # Patched to import our models + settings
├── scripts/
│   └── discover_endpoints.py        # Playwright network discovery
├── data/
│   ├── raw/                         # Raw JSON payloads (gitignored)
│   └── exports/                     # (empty)
├── tests/                           # (empty)
├── .env.example
├── .gitignore
├── alembic.ini
├── docker-compose.yml               # PostgreSQL on port 5433
├── pyproject.toml
├── discovery_report.json             # Full Playwright discovery output (gitignored)
└── README.md
```

---

## 6. How to Run

```powershell
# 1. Start PostgreSQL
docker compose up -d

# 2. Activate venv
.\.venv\Scripts\activate

# 3. Run migrations (only needed once or after model changes)
alembic upgrade head

# 4. Single collection
python -m app.main collect-once

# 5. Continuous collection (Ctrl+C to stop)
python -m app.main run

# 6. Re-run discovery (optional)
python scripts/discover_endpoints.py
```

---

## 7. Known Issues

1. **`version` attribute warning** in docker-compose.yml — remove the `version: '3.8'` line, it's obsolete.
2. **Results parsing** is incomplete — the actual results API response structure needs verification.
3. **No `.env` file** exists — the app uses defaults from `settings.py`. Create one from `.env.example` if needed.
4. **`virtual_league_collector.egg-info/`** was committed to git — should be added to `.gitignore`.
5. **League ID mismatch**: The `get_or_create_league` creates league with `external_id=8065` but assigns an internal `id` of 2 (because it was called twice during testing). This is fine but be aware that `league.id != league.external_id`.

---

## 8. Constraints Reminder

- **DO NOT** place bets, bypass auth/CAPTCHA, use stealth techniques, or circumvent rate limits
- **DO NOT** fabricate data or infer information not in the source
- Respect robots.txt and reasonable request rates
- Use **UTC** internally for all timestamps
- **RAW DATA > DERIVED DATA** — always preserve the original API response
- **NO data leakage** in ML features — every feature must be from BEFORE the match
