# Virtual League Collector

A production-quality data collection system for a virtual football betting research project.

**League**: World Cup / Instant League (ID: `8065`) on [bet261.mg](https://bet261.mg)

**Purpose**: Create trustworthy, chronological, reproducible datasets for statistical analysis, ML backtesting, and prediction research.

**NOT** for placing bets.

---

## Table of Contents

1. [Overview](#overview)
2. [Features](#features)
3. [Architecture](#architecture)
4. [Prerequisites](#prerequisites)
5. [Installation](#installation)
6. [Configuration](#configuration)
7. [Database Setup](#database-setup)
8. [Usage](#usage)
9. [CLI Commands](#cli-commands)
10. [API Endpoints](#api-endpoints)
11. [Database Schema](#database-schema)
12. [Data Pipeline](#data-pipeline)
13. [Testing](#testing)
14. [Docker](#docker)
15. [Development](#development)
16. [Data Validation](#data-validation)
17. [Export Formats](#export-formats)
18. [Troubleshooting](#troubleshooting)
19. [Contributing](#contributing)
20. [License](#license)

---

## Overview

This system collects data from the bet261.mg virtual football API to create a comprehensive dataset for research. It tracks:

- **Matches**: Upcoming fixtures with odds from 20+ betting markets
- **Results**: Completed matches with scores, half-time scores, and goal events
- **Rankings**: League standings with form history
- **Playout**: Minute-by-minute goal events

The system is designed for reproducibility: every API response is saved to disk and referenced in the database.

---

## Features

- **Automated Collection**: Continuous or one-shot data collection
- **Smart Deduplication**: Prevents duplicate records using stable external IDs
- **Odds History**: Tracks odds changes over time (only saves when odds change)
- **Match Reconciliation**: Links results back to original match records
- **Graceful Shutdown**: Handles SIGINT/SIGTERM for clean shutdown
- **Retry Logic**: Exponential backoff with tenacity for API resilience
- **Data Validation**: Built-in integrity checks and temporal leakage detection
- **Export**: Generate CSV and Parquet files for analysis
- **ML Dataset**: Integrated dataset with pre-match features only

---

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed system architecture.

---

## Prerequisites

- Python 3.12+
- PostgreSQL 15+
- Docker (optional, for database)

---

## Installation

```bash
# Clone the repository
git clone https://github.com/FetraFex/bet261-scrapping-virtual.git
cd bet261-scrapping-virtual

# Create virtual environment
python -m venv .venv
.\.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -e .

# Install dev dependencies (optional)
pip install -e ".[dev]"
```

---

## Configuration

The application uses `pydantic-settings` to manage configuration. Create a `.env` file in the project root:

```bash
cp .env.example .env
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5433/virtual_league` | PostgreSQL connection string |
| `LEAGUE_ID` | `8065` | League ID (World Cup) |
| `LEAGUE_NAME` | `World Cup` | League display name |
| `POLL_INTERVAL_SECONDS` | `10` | Seconds between collection cycles |
| `REQUEST_TIMEOUT_SECONDS` | `20` | HTTP request timeout |
| `MAX_RETRIES` | `3` | Maximum retry attempts |
| `RAW_DATA_DIR` | `./data/raw` | Directory for raw JSON payloads |
| `LOG_LEVEL` | `INFO` | Logging level |

---

## Database Setup

### Option 1: Docker (Recommended)

```bash
# Start PostgreSQL
docker compose up -d

# Check status
docker compose ps
```

### Option 2: Local PostgreSQL

If you have PostgreSQL running on port 5432, update `DATABASE_URL` in `.env`:

```
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/virtual_league
```

### Run Migrations

```bash
# Apply all migrations
alembic upgrade head
```

---

## Usage

### Single Collection

```bash
python -m app.main collect-once
```

### Continuous Collection

```bash
python -m app.main run
```

Press `Ctrl+C` to stop gracefully.

### View Status

```bash
python -m app.main status
```

### Export Data

```bash
python -m app.main export
```

### Validate Data

```bash
python -m app.main validate
```

### Backfill Historical Data

```bash
python -m app.main backfill --rounds 10
```

---

## CLI Commands

| Command | Description | Example |
|---------|-------------|---------|
| `collect-once` | Single collection cycle | `python -m app.main collect-once` |
| `run` | Continuous collection | `python -m app.main run` |
| `status` | Show database statistics | `python -m app.main status` |
| `export` | Generate CSV/Parquet files | `python -m app.main export` |
| `validate` | Check data integrity | `python -m app.main validate` |
| `backfill` | Fetch historical data | `python -m app.main backfill --rounds 10` |

---

## API Endpoints

| Data | Endpoint | Description |
|------|----------|-------------|
| Matches | `GET /instantleagues/8065/matches` | Upcoming matches with odds |
| Results | `GET /instantleagues/8065/results` | Completed matches with scores |
| Ranking | `GET /instantleagues/8065/ranking` | League standings |
| Playout | `GET /instantleagues/round/{N}/playout` | Goal events for a round |

---

## Database Schema

### Core Tables

- **leagues**: League metadata
- **teams**: Team registry with normalized names
- **matches**: Match records with status tracking
- **odds_snapshots**: Historical odds (saved only when odds change)
- **match_events**: Goal events with minute-by-minute data
- **ranking_snapshots**: Standings state at a point in time
- **ranking_entries**: Individual team rankings within snapshots

### Operational Tables

- **raw_payloads**: References to raw JSON files on disk
- **collection_runs**: Collection cycle tracking
- **scraper_errors**: Error logging per source

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed schema documentation.

---

## Data Pipeline

```
API Response
    ↓
Save to disk (data/raw/{type}/YYYY/MM/DD/*.json)
    ↓
Record reference in raw_payloads table
    ↓
Parse and validate with Pydantic
    ↓
Deduplicate / reconcile with existing data
    ↓
Save to PostgreSQL
    ↓
Export to CSV/Parquet (optional)
```

---

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=app

# Run specific test file
pytest tests/test_schemas.py -v
```

### Test Coverage

- Pydantic schema validation
- Team name normalization
- SHA-256 hashing
- Score string parsing
- Temporal leakage detection
- Match result determination

---

## Docker

### Build Image

```bash
docker build -t virtual-league-collector .
```

### Run Container

```bash
# Single collection
docker run --rm virtual-league-collector

# Continuous collection
docker run --rm virtual-league-collector python -m app.main run

# With environment variables
docker run --rm -e DATABASE_URL=postgresql://... virtual-league-collector
```

### Docker Compose (Full Stack)

```bash
# Start both PostgreSQL and collector
docker compose up -d

# Run collector
docker compose exec postgres python -m app.main collect-once
```

---

## Development

### Code Style

```bash
# Format code
black app/ tests/

# Sort imports
isort app/ tests/

# Lint
ruff check app/ tests/
```

### Adding Migrations

```bash
# Generate migration
alembic revision --autogenerate -m "description"

# Apply migration
alembic upgrade head

# Rollback
alembic downgrade -1
```

---

## Data Validation

The `validate` command checks:

- Matches without odds snapshots
- Completed matches without scores
- UPCOMING matches with scores (data inconsistency)
- Duplicate external IDs
- Temporal leakage (odds captured after match completion)

---

## Export Formats

### CSV Files

- `matches.csv` - All match records
- `odds_snapshots.csv` - Historical odds
- `match_events.csv` - Goal events
- `ranking_snapshots.csv` - Ranking snapshots
- `ranking_entries.csv` - Individual rankings
- `collection_runs.csv` - Collection history

### ML Dataset

The `ml_dataset.csv` includes:

- Match details (teams, scheduled time, result)
- Opening and closing odds
- Implied probabilities
- Team names (resolved from IDs)

---

## Troubleshooting

### Database Connection Issues

```bash
# Check if PostgreSQL is running
docker compose ps

# Check connection
psql -h localhost -p 5433 -U postgres -d virtual_league
```

### API Request Failures

The system uses exponential backoff with 3 retries. Check logs for details:

```bash
# Run with debug logging
LOG_LEVEL=DEBUG python -m app.main collect-once
```

### Migration Errors

```bash
# Check current migration
alembic current

# Force upgrade
alembic upgrade head --sql
```

---

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Run `pytest tests/ -v`
6. Submit a pull request

---

## License

This project is for research purposes only. See the repository for license details.

---

## Acknowledgments

- Data source: [bet261.mg](https://bet261.mg)
- API discovery via Playwright network interception
- Built with FastAPI, SQLAlchemy, and Pydantic
