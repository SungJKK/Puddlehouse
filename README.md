# Local Data Lakehouse

A local data lakehouse built from scratch, combining Parquet files, a lightweight metadata catalog, orchestration, transformation, and distributed compute. The entire stack runs locally via Docker Compose — no cloud account or managed service required.

## Running
```
$ python -m [scripts.init_catalog]
$ python -m tests.smoke_test
```

## Stack

| Layer | Tool | Role |
|---|---|---|
| Storage Format | Parquet | Columnar file format for all lakehouse data (via PyArrow) |
| Query Engine | DuckDB | Fast local OLAP queries directly on Parquet files |
| Metadata Catalog | SQLite | Hand-rolled local catalog (tracks table metadata, snapshots, lineage, and partitions) |
| Orchestration | Dagster | Pipeline orchestration, asset management, and observability |
| Transformation | dbt | SQL-based data modeling and transformation layer |
| Compute | Apache Spark | Distributed processing for large-scale ingestion and transformation |
| Streaming | Apache Kafka | Event streaming for real-time data ingestion into the lakehouse |
| Containerization | Docker Compose | Runs and networks all services locally as isolated containers |

## Architecture

```
Raw Sources          Streaming Events
    │                      │
    │                      ▼
    │              [Kafka Topics]
    │                      │
    ▼                      │
[Dagster] ─── orchestrates ──────────────────────────────┐
    │                      │                              │
    ├──► [Spark] ◄─────────┘                             │
    │      ├── batch ingest ──► Parquet files (Bronze)   │
    │      └── stream ingest ─► Parquet files (Bronze)   │
    │                                   │                 │
    ├──► [dbt + DuckDB] ────────────────► Parquet files (Silver/Gold)
    │         (transform & model)                         │
    │                                                     │
    └──► [SQLite Catalog] ◄── tracks all Parquet metadata ┘
              (namespaces, table locations, snapshots)

[DuckDB] ──► ad-hoc queries on any Parquet file
```

### Medallion Layers

- **Bronze** — Raw ingested data, append-only, minimal transformation
- **Silver** — Cleaned, deduplicated, conformed data
- **Gold** — Aggregated, business-ready models

## Docker Services

Each component runs in its own container. All services are defined in `docker-compose.yml` and share a Docker network (`lakehouse-net`) and a named volume (`warehouse`) for Parquet data files.

| Service | Container | Ports |
|---|---|---|
| Dagster Webserver | `dagster-webserver` | `3000` |
| Dagster Daemon | `dagster-daemon` | — |
| Spark Master | `spark-master` | `8080` (UI), `7077` |
| Spark Worker | `spark-worker` | `8081` (UI) |
| Kafka Broker | `kafka` | `9092` |
| Zookeeper | `zookeeper` | `2181` |
| dbt Runner | `dbt` | — (runs as a job) |

> SQLite and the `warehouse/` data files live on a shared Docker volume mounted into the Dagster, Spark, and dbt containers so all services see the same Parquet files and catalog.

## Project Structure

```
lakehouse/
├── docker-compose.yml          # Defines and networks all services
├── .env                        # Environment variables (ports, paths, credentials)
│
├── catalog/
│   ├── Dockerfile              # Lightweight image with PyArrow + SQLite
│   └── catalog.db              # SQLite catalog file (gitignored, lives on volume)
│
├── dagster/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── dagster.yaml            # Dagster instance config
│   └── lakehouse/
│       ├── assets/             # Dagster software-defined assets
│       ├── jobs/               # Job definitions
│       ├── resources/          # Shared resources (SQLite catalog, Spark session)
│       └── __init__.py
│
├── dbt/
│   ├── Dockerfile
│   ├── dbt_project.yml
│   ├── profiles.yml            # DuckDB connection profile
│   └── models/
│       ├── silver/             # Silver layer models
│       └── gold/               # Gold layer models
│
├── kafka/
│   ├── Dockerfile              # Custom Kafka image if needed
│   └── config/
│       └── topics.yml          # Topic definitions (name, partitions, retention)
│
├── spark/
│   ├── Dockerfile              # Spark image pre-installed
│   └── jobs/                   # PySpark batch and streaming job scripts
│
├── warehouse/                  # Parquet data files and metadata
│   └── .gitkeep                # Keeps dir in git; actual data is gitignored
│
├── scripts/
│   ├── init_catalog.py         # Bootstrap SQLite catalog with namespaces/tables
│   └── seed_kafka.py           # Publish sample events to Kafka topics
│
├── pyproject.toml              # Python deps managed by uv (for local dev)
└── README.md
```

## Getting Started

### Prerequisites

- Docker & Docker Compose
- `uv` (for local development outside containers)

### Quick Start

```bash
# Clone the repo
git clone <repo-url>
cd lakehouse

# Copy environment defaults
cp .env.example .env

# Build and start all services
docker compose up --build

# Initialize the catalog (first run only)
docker compose exec dagster-webserver python scripts/init_catalog.py
```

### Local Development (without Docker)

```bash
# Create and activate the Python environment
uv sync
source .venv/bin/activate

# Run a script directly
uv run python scripts/init_catalog.py
```

### Service UIs

| Service | URL |
|---|---|
| Dagster | http://localhost:3000 |
| Spark Master | http://localhost:8080 |
| Spark Worker | http://localhost:8081 |

## Design Decisions

- **SQLite as catalog**: Avoids running a heavyweight catalog service (Hive Metastore, Nessie) locally. A hand-rolled catalog (`catalog/`) manages tables, snapshots, lineage, and partitions directly via `sqlite3`.
- **DuckDB for queries**: Reads Parquet files directly via `read_parquet()` — no Spark needed for ad-hoc analysis.
- **Spark for ingestion**: Handles large-scale or complex ingestion jobs where DuckDB's single-node limits apply.
- **Dagster over Airflow**: Asset-centric model fits the lakehouse paradigm better than task-centric DAGs.
- **dbt on DuckDB**: Lightweight transformation layer; dbt models run via `dbt-duckdb` adapter directly against Parquet files.
- **Kafka for streaming**: Decouples event producers from the lakehouse. Spark Structured Streaming consumes Kafka topics and writes to Parquet Bronze files, enabling both batch and real-time ingestion paths.
- **Docker Compose over Kubernetes**: Keeps local dev simple. Each service has its own Dockerfile for future portability to a Kubernetes or cloud deployment.
- **Shared volume for warehouse**: A single named Docker volume (`warehouse`) is mounted into all containers that read/write Parquet files, ensuring catalog and data files stay consistent across services.

## Status

Work in progress — initial setup phase.

---

## Build Phases

A bottom-up build order — each phase produces something testable before the next begins.

---

