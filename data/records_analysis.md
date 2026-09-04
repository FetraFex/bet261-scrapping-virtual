# Saved Raw Records Analysis

> **Generated**: 2026-08-25  
> **Source Files**: `data/raw/` directory  
> **League**: World Cup / Instant League (ID: 8065)

---

## Files Discovered

| Type | Path | Timestamp | Hash |
|------|------|-----------|------|
| Matches | `data/raw/matches/2026/08/24/20260824_225906_fa0e4736.json` | 2026-08-24 22:59:06 | fa0e4736 |
| Matches | `data/raw/matches/2026/08/24/20260824_230210_acdfb333.json` | 2026-08-24 23:02:10 | acdfb333 |
| Matches | `data/raw/matches/2026/08/24/20260824_230241_84d7c45c.json` | 2026-08-24 23:02:41 | 84d7c45c |
| Ranking | `data/raw/ranking/2026/08/24/20260824_230212_a2ced92f.json` | 2026-08-24 23:02:12 | a2ced92f |
| Ranking | `data/raw/ranking/2026/08/24/20260824_230243_5400ef56.json` | 2026-08-24 23:02:43 | 5400ef56 |
| Results | `data/raw/results/2026/08/24/20260824_230212_5ae6ec51.json` | 2026-08-24 23:02:12 | 5ae6ec51 |
| Results | `data/raw/results/2026/08/24/20260824_230242_15b687c5.json` | 2026-08-24 23:02:42 | 15b687c5 |

**Total**: 3 matches files, 2 ranking files, 2 results files (7 raw payloads)

---

## 1. Matches API Response Structure

**Endpoint**: `GET /instantleagues/8065/matches`  
**Base URL**: `https://hg-event-api-prod.sporty-tech.net/api`

### Top-Level Structure

```json
{
  "rounds": [ ... ]
}
```

### Round Object

```json
{
  "expectedStart": "2026-08-24T22:59:18Z",   // ISO 8601 UTC
  "expectedEnd": "0001-01-01T00:00:00Z",      // Zeros for future rounds
  "roundNumber": 13,                           // Integer
  "matches": [ ... ]                           // Array (empty for future rounds)
}
```

### Match Object

```json
{
  "id": 76837631,              // Stable external match ID (integer)
  "entryPointId": 8065,        // League ID
  "round": "13",               // Round number as string
  "name": "Morocco vs Algeria", // Match name
  "awayTeam": {
    "name": "Algeria",
    "points": 0,
    "position": 0,
    "won": 0,
    "lost": 0,
    "draw": 0
  },
  "homeTeam": {
    "name": "Morocco",
    "points": 0,
    "position": 0,
    "won": 0,
    "lost": 0,
    "draw": 0
  },
  "expectedStart": "0001-01-01T00:00:00Z",   // Zeros for upcoming matches
  "eventBetTypes": [ ... ]                    // Array of bet type objects
}
```

### EventBetType Object (Odds)

```json
{
  "id": 2234245454,
  "eventId": 76837631,
  "name": "1X2",               // Bet type name
  "eventBetTypeItems": [ ... ], // Array of odds items
  "betTypeId": 30083,
  "isAsian": false,
  "baseAmount": 1000.0,
  "minimumAmountIncrement": 1.0,
  "maximumAmount": 100000.0,
  "active": true,
  "bettingAllowed": true,
  "displayPriority": 1,
  "hasExplanations": false,
  "canBeSimulated": false,
  "isManual": false,
  "allowBetBuilder": false
}
```

### EventBetTypeItem Object (Individual Odds)

```json
{
  "id": 10222202627,
  "eventBetTypeId": 2234245454,
  "shortName": "1",             // "1" = Home, "X" = Draw, "2" = Away
  "odds": 1.67,                // Decimal odds
  "active": true,
  "bettingAllowed": true,
  "canBeSimulated": false
}
```

### Bet Types Found Per Match

| Priority | Name | Market |
|----------|------|--------|
| 1 | `1X2` | Home/Draw/Away |
| 2 | `Mi-tps 1X2` | Half-time 1X2 |
| 3 | `Double Chance` | 1X/X2/12 |
| 4 | `Mi-tps DC` | Half-time Double Chance |
| 99 | `Score exact` | Correct score (0-0 to 6-0) |
| 99 | `Mi-tps CS` | Half-time correct score |
| 99 | `+/-` | Over/Under (0.5, 1.5, 2.5, 3.5) |
| 99 | `HT/FT` | Half-time/Full-time |
| 99 | `Total de buts` | Total goals (0-6) |
| 99 | `G/NG` | Both teams to score |
| 99 | `Les deux équipes marquent / 1ère mi temps` | BTTS 1st half |
| 99 | `1X2 & Total` | 1X2 combined with O/U |
| 99 | `1X2 & G/NG` | 1X2 combined with BTTS |
| 99 | `Total equipe domicile` | Home team total (O/U) |
| 99 | `Total equipe extérieur` | Away team total (O/U) |
| 99 | `G/NG equipe domicile` | Home BTTS |
| 99 | `G/NG equipe extérieur` | Away BTTS |
| 99 | `Pair/Impair` | Odd/Even goals |
| 99 | `Minute du premier but` | First goal minute range |
| 99 | `FTTS` | First team to score |
| 99 | `Multi-Buts` | Multi-goals |
| 99 | `2ème mi-tps - CS` | 2nd half correct score |

---

## 2. Results API Response Structure

**Endpoint**: `GET /instantleagues/8065/results?skip=0&take=20`

### Top-Level Structure

```json
{
  "rounds": [ ... ]
}
```

### Round Object

```json
{
  "expectedStart": "2026-08-24T22:59:18Z",
  "expectedEnd": "0001-01-01T00:00:00Z",
  "roundNumber": 13,
  "matches": [ ... ],
  "id": 0,
  "eventCategoryId": 0
}
```

### Result Match Object (IMPORTANT — Different from Matches API!)

```json
{
  "id": 0,                            // ⚠️ ALWAYS 0 in results! Not a stable ID
  "entryPointId": 0,                   // ⚠️ ALWAYS 0 in results!
  "name": "Morocco vs Algeria",
  "awayTeam": {
    "name": "Algeria",
    "points": 0,
    "position": 0,
    "won": 0,
    "lost": 0,
    "draw": 0
  },
  "homeTeam": {
    "name": "Morocco",
    "points": 0,
    "position": 0,
    "won": 0,
    "lost": 0,
    "draw": 0
  },
  "goals": [                          // ⚠️ KEY FIELD — Not present in Matches API
    {
      "minute": 87,                   // Goal minute
      "homeScore": 1.0,              // Home score AFTER this goal
      "awayScore": 0.0,              // Away score AFTER this goal
      "team": "Home"                 // "Home" or "Away"
    },
    {
      "minute": 88,
      "homeScore": 1.0,
      "awayScore": 1.0,
      "team": "Away"
    }
  ],
  "score": "1:1",                     // ⚠️ Final score as string
  "halfTimeScore": "0:0",             // ⚠️ Half-time score as string
  "expectedStart": "2026-08-24T22:59:18Z"
}
```

### ⚠️ Critical Differences from Matches API

| Field | Matches API | Results API |
|-------|------------|-------------|
| `id` | Real external match ID (e.g., 76837631) | **Always 0** |
| `entryPointId` | 8065 | **Always 0** |
| `goals` | **Not present** | Array of goal events |
| `score` | **Not present** | String like "1:1" |
| `halfTimeScore` | **Not present** | String like "0:0" |
| `eventBetTypes` | Array of odds | **Not present** |
| `round` | String | Integer in parent |

### ⚠️ Deduplication Implication

The results API does NOT provide a stable `id` field (always 0). To match results to matches:
1. Use **team names + round number + expectedStart** as composite key
2. Or match by `name` field (e.g., "Morocco vs Algeria")

### Sample Results Data

**Round 13** (24 matches):
- Morocco vs Algeria: 1:1 (HT: 0:0) — Goals: 87' (Home), 88' (Away)
- Tunisia vs Australia: 1:1 (HT: 1:1) — Goals: 40' (Away), 41' (Home)
- Mexico vs Switzerland: 1:1 (HT: 0:1) — Goals: 21' (Away), 89' (Home)
- Portugal vs Qatar: 1:4 (HT: 1:2) — Goals: 39' (Home), 40' (Away), 44' (Away), 53' (Away), 81' (Away)
- Spain vs Austria: 5:0 (HT: 3:0) — Goals: 11', 25', 43', 53', 65' (all Home)

**Round 12** (24 matches):
- Spain vs Austria: 5:0 (HT: 3:0)
- England vs Belgium: 2:1 (HT: 2:0)
- Canada vs Czechia: 3:1 (HT: 1:1)

---

## 3. Ranking API Response Structure

**Endpoint**: `GET /instantleagues/8065/ranking`

### Top-Level Structure

```json
{
  "teams": [ ... ]
}
```

### Team Object

```json
{
  "name": "Spain",                    // Team name
  "points": 32,                       // League points
  "position": 1,                      // Rank position
  "history": [                        // Last 5 results
    "Draw",
    "Won",
    "Won",
    "Won",
    "Won"
  ],
  "won": 10,                          // Total wins
  "lost": 1,                          // Total losses
  "draw": 2                           // Total draws
}
```

### Sample Rankings (Top 10)

| Pos | Team | Pts | W | L | D | History |
|-----|------|-----|---|---|---|---------|
| 1 | Spain | 32 | 10 | 1 | 2 | D W W W W |
| 2 | France | 31 | 9 | 0 | 4 | D W W W W |
| 3 | England | 29 | 9 | 2 | 2 | D W W W L |
| 4 | Czechia | 27 | 8 | 2 | 3 | W L D L W |
| 5 | Argentina | 24 | 6 | 1 | 6 | D D W L W |
| 6 | Sweden | 24 | 7 | 3 | 3 | W D D L W |
| 7 | Canada | 24 | 7 | 3 | 3 | W W W D D |
| 7 | Senegal | 24 | 7 | 3 | 3 | W D L L W |
| 9 | USA | 24 | 6 | 1 | 6 | D D D L W |
| 10 | Egypt | 23 | 7 | 4 | 2 | W W D W D |

### Total Teams: 48

---

## 4. Database Schema Mapping

### Matches → `matches` table

| API Field | DB Column | Notes |
|-----------|-----------|-------|
| `id` | `external_id` | Stable external ID |
| `entryPointId` | `league_id` | Always 8065 |
| `name` | N/A | Derive from teams |
| `homeTeam.name` | `home_team_id` | FK to teams table |
| `awayTeam.name` | `away_team_id` | FK to teams table |
| `round` | `round_number` | String → Integer |
| `expectedStart` | `scheduled_at` | ISO 8601 → UTC datetime |

### Results → `matches` table (UPDATE)

| API Field | DB Column | Notes |
|-----------|-----------|-------|
| `name` | match lookup | Used for reconciliation |
| `score` | `home_score`, `away_score` | Parse "1:1" → ints |
| `halfTimeScore` | `half_home_score`, `half_away_score` | Parse "0:0" → ints |
| `goals` | `match_events` table | Each goal = 1 row |

### Goals → `match_events` table

| API Field | DB Column | Notes |
|-----------|-----------|-------|
| `minute` | `minute` | Integer |
| `homeScore` | `home_score` | Score after goal |
| `awayScore` | `away_score` | Score after goal |
| `team` | `scoring_team` | "Home" or "Away" |

### Ranking → `ranking_snapshots` + `ranking_entries` tables

| API Field | DB Table | DB Column | Notes |
|-----------|----------|-----------|-------|
| (top-level) | `ranking_snapshots` | `league_id` | 8065 |
| (top-level) | `ranking_snapshots` | `captured_at` | UTC now |
| `name` | `ranking_entries` + `teams` | FK | Team lookup |
| `points` | `ranking_entries` | `points` | Integer |
| `position` | `ranking_entries` | `position` | Integer |
| `won` | `ranking_entries` | `won` | Integer |
| `lost` | `ranking_entries` | `lost` | Integer |
| `draw` | `ranking_entries` | `draw` | Integer |
| `history` | `ranking_entries` | `form` | JSON array |

---

## 5. Key Observations

### ✅ What Works
1. **Matches API** — Clean structure, stable `id` field for deduplication
2. **Odds** — Rich data with 20+ bet types per match
3. **Ranking** — Full standings with form history
4. **Results** — Includes goals array and half-time scores (already available!)

### ⚠️ Issues to Address
1. **Results `id` is always 0** — Cannot use for deduplication; must use team names + round
2. **Results `entryPointId` is always 0** — League ID not provided
3. **Half-time scores available** — `halfTimeScore` field already in results (no need to derive from goals)
4. **Match reconciliation** — Must match results to matches by team names + expectedStart

### 🔧 Code Changes Needed

1. **Fix results parser** — Handle `id: 0` and `entryPointId: 0`
2. **Parse `score` string** — Split "1:1" into `home_score=1`, `away_score=1`
3. **Parse `halfTimeScore` string** — Split "0:0" into `half_home_score=0`, `half_away_score=0`
4. **Parse goals array** — Each goal → `match_events` row
5. **Match reconciliation** — Use `name` field (team names) + `roundNumber` to link results to matches

---

## 6. Raw Data Volume Summary

| Data Type | Files | Matches/Rounds | Teams |
|-----------|-------|----------------|-------|
| Matches | 3 files | 2 rounds (12-13) | 48 teams |
| Results | 2 files | 3 rounds (11-13) | 48 teams |
| Ranking | 2 files | 1 snapshot | 48 teams |
| **Total** | **7 files** | — | **48 teams** |

---

*This document was auto-generated from raw API payloads saved in `data/raw/`.*
