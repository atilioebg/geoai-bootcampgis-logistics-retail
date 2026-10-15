# BootcampGIS — GeoAI Stack

Welcome to the **BootcampGIS GeoAI Stack** repository! Developed by **Dr. Atilio Efrain Bica Grondona** for the **BootcampGIS GeoAI: Logistics & Retail Site Selection** curriculum, this project combines a state-of-the-art Multi-Agent AI system (Actor-Critic Swarm) with a robust enterprise spatial database infrastructure (PostGIS + pgvector + Apache AGE) and an interactive web mapping dashboard (Streamlit + Folium) to solve complex geospatial problems.

---

## 🏗️ Architecture Overview

The project is structured into four integrated tiers that bridge cognitive AI reasoning with high-performance spatial database operations:

---

## 🔄 End-to-End Solution Flowchart

The diagram below illustrates the end-to-end data lifecycle: from natural language user input in Streamlit, through the LangGraph Swarm and specialized spatial tools, into the containerized GeoStack backend, and back to the Folium interactive map canvas.

```mermaid
flowchart TD
    subgraph UI["🖥️ Presentation Tier (Streamlit & Folium)"]
        User(["👤 User / GIS Decision Maker"])
        ChatUI["💬 Streamlit Chat Interface\n(Control Panel & Session Memory)"]
        MapView["🗺️ Folium Map Canvas\n(Dynamic Bounding, Red Star Winner & Catchments)"]
    end

    subgraph Swarm["🤖 Agentic Orchestration Tier (LangGraph & Gemini)"]
        GraphEngine["LangGraph StateGraph\n(SwarmState TypedDict)"]
        MetadataCache[("🧠 Cognitive Blueprint Cache\n(pg_description + business_rules)")]
        PlannerAgent["📋 Planner Node\n(Tool Planning & Reasoning)"]
        WorkerAgent["⚙️ Worker Node (Actor)\n(ReAct Tool Execution Loop)"]
        ReviewerAgent["🧐 Reviewer Node (Critic)\n(GIS Sensor & Critique)"]
    end

    subgraph Tools["🛠️ Specialized LangChain Tool Registry"]
        T1["calculate_optimal_logistics_hub\n(Centroid Snapping & Buffers)"]
        T2["find_geomarketing_gaps\n(Demographic Anti-Joins)"]
        T3["semantic_search_tool\n(pgvector Cosine Search)"]
        T4["knowledge_graph_tool\n(Apache AGE Cypher Traversal)"]
        T5["get_route_distance_time\n(Google Routes API v2)"]
        T6["submit_final_response\n(Terminal Payload Delivery)"]
    end

    subgraph Backend["🏢 Enterprise GeoStack & Cloud Services"]
        Postgres[("🐘 PostgreSQL 16 + PostGIS 3.4\n- pgvector v0.6.2 (Reviews)\n- Apache AGE (Knowledge Graph)\n- ACS Census & TIGER Datasets")]
        GeoServer["🗺️ GeoServer Tile Server\n(Port 8080 - WMS / WFS)"]
        GoogleAPI["🌐 Google Cloud Routes API v2\n(Road Matrix & Transit Durations)"]
    end

    %% Interactions
    User -->|"Prompt (Spatial Query)"| ChatUI
    ChatUI -->|"Execute Query"| GraphEngine
    MetadataCache -.->|"One-Shot Schema Injection"| GraphEngine
    GraphEngine --> PlannerAgent
    PlannerAgent --> WorkerAgent
    WorkerAgent <-->|"ReAct Tool Loop"| Tools
    WorkerAgent --> ReviewerAgent

    %% Tool execution connections
    T1 -->|"SQL Queries"| Postgres
    T2 -->|"Spatial Joins"| Postgres
    T3 -->|"Cosine Distance (<=>)"| Postgres
    T4 -->|"Cypher Traversal"| Postgres
    T5 -->|"REST API Call"| GoogleAPI
    T6 -->|"Final Response & Payloads"| GraphEngine

    %% Delivery back to UI
    GraphEngine -->|"Analytical Summary & Metrics"| ChatUI
    GraphEngine -->|"frontend_payload (GeoJSON, Pins, Winner)"| MapView
    GeoServer -.->|"WMS Map Tiles"| MapView
```

---

### 1. GeoAI Agent Swarm Architecture (Flowchart)

Powered by **LangGraph** and **Google Gemini**, the AI architecture implements an **Actor-Critic Swarm** with self-healing retry cycles, deterministic spatial sensors, and **Cognitive Blueprint schema awareness**:

```mermaid
flowchart TD
    Start(["🚀 START"]) --> Planner["📋 Planner Node\n(Gemini with_structured_output: PlannerOutput)"]

    subgraph S1["1. Planning Phase"]
        Planner -->|"Structured Output: List of Tools\n(Single-pass: never re-loops)"| PlanState["State: plan [tools]"]
    end

    subgraph S2["2. Actor Phase (Worker)"]
        PlanState --> Worker["⚙️ Worker Node (Actor)\n- Injects Schema Context & Reviewer Feedback\n- ReAct Tool Execution Loop (max 5 iter)\n- Generates CoT Analysis & Recommendations\n- Calls submit_final_response"]
        ToolRegistry[("🛠️ Tool Registry\nPostGIS | pgvector | AGE | Routes")] <-->|"Execute & Observe"| Worker
    end

    subgraph S3["3. Critic & Sensor Phase (Reviewer)"]
        Worker -->|"draft_response + tool_payload"| Sensor{"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;🔍 Deterministic GIS Sensor (_validate_gis_agent)&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<br/>Valid coordinates, payload & execution?"}
        
        Sensor -->|"Passed Sensor"| ReviewerLLM["🧐 Reviewer Node (Critic)\n- Gemini critique via ReviewerOutput\n- Increments loop_count (+1)"]
        Sensor -->|"Failed Sensor"| SensorFail["Force review_status = 'rejected'\nwith corrective feedback"]
        SensorFail --> ReviewerLLM
    end

    subgraph S4["4. Self-Healing Routing Phase"]
        ReviewerLLM --> Decision{"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;route_from_reviewer&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<br/>(Conditional Edge)"}
        Decision -->|"Approved"| Success(["🏁 END\n(Deliver to Streamlit & Folium)"])
        Decision -->|"Rejected\n& loop_count < 3"| Worker
        Decision -->|"Rejected\n& loop_count >= 3"| Brake["🚨 Emergency Brake Node\n(System fallback safety cutoff)"]
        Brake --> Fallback(["⚠️ END\n(Deliver Error Notification)"])
    end
```

- **Planner Node:** Receives the user question once and decomposes it into an ordered execution plan (list of tools) using `.with_structured_output(PlannerOutput)`. Does not re-loop.
- **Worker Node (Actor):** Executes planned tools inside a ReAct loop (max 5 iterations). Reads Reviewer feedback on retry cycles and incorporates it into the prompt context. Concludes analysis by calling `submit_final_response` with structured analytical reasoning, candidate rankings, and the top winner.
- **Deterministic GIS Sensor (`_validate_gis_agent`):** Pre-LLM Python sensor that deterministically verifies (1) non-empty tool payloads, (2) presence of valid latitude/longitude coordinates, and (3) execution success, rejecting malformed drafts immediately without wasting LLM tokens.
- **Reviewer Node (Critic):** Evaluates the worker's draft against the original prompt using `.with_structured_output(ReviewerOutput)`. Combines LLM validation with the deterministic Python sensor to ensure spatial coordinates and GeoJSON features are never dropped. Enforces a 3-retry safety cap via `loop_count`.
- **Emergency Brake Node:** Gracefully captures failures if the self-healing loop reaches the maximum 3-retry threshold, preventing infinite token-draining loops.

---

### 2. LangChain Tool Registry (Specialized Spatial Tools)

| Tool | Module | Backend & Operations |
|---|---|---|
| `get_route_distance_time` | `src/agent/tools/api_tools.py` | Google Routes API v2 (POST payload, FieldMasks, km/min parsing) |
| `calculate_optimal_logistics_hub` | `src/agent/tools/spatial_tools.py` | PostGIS (`ST_Union`, `ST_Centroid`, `ST_ClosestPoint`, `ST_Buffer`) |
| `find_geomarketing_gaps` | `src/agent/tools/spatial_tools.py` | PostGIS (`ST_Buffer`, `ST_Intersects`, spatial anti-joins on income tracts) |
| `semantic_search_tool` | `src/agent/tools/rag_tools.py` | pgvector cosine similarity (`<=>`) with `bge-large-en-v1.5` embeddings |
| `knowledge_graph_tool` | `src/agent/tools/rag_tools.py` | Apache AGE Cypher graph traversals (`MATCH (p:Place)-[:SERVES]->(c:Cuisine)`) |
| `submit_final_response` | `src/agent/agents/worker.py` | Structured terminal payload delivery tool for the Worker agent |

---

### 3. Interactive Geospatial Dashboard (Streamlit + Folium)

A responsive 75/25 split-screen interface tailored for geospatial decision-makers:

- **75% Map Canvas ([`src/frontend/map_utils.py`](src/frontend/map_utils.py)):** Folium map supporting dynamic bounding box auto-centering, candidate POI pins with custom HTML popups, prominent red star winner markers, logistics catchment buffer polygons, and GeoServer WMS layers.
- **25% Agent Control Panel ([`src/frontend/app.py`](src/frontend/app.py)):** Session memory management, real-time message history, agent thinking progress, and session restart capabilities.

---

### 4. Enterprise GeoStack Infrastructure (Docker)

A fully containerized spatial backend built on a **custom PostgreSQL 16 image**:

| Service | Image / Build | Port | Purpose |
|---|---|---|---|
| `db` | Custom `scripts/geostack/postgis/Dockerfile` | 5432 | PostgreSQL 16 + PostGIS 3.4 + pgvector v0.6.2 + Apache AGE |
| `geoserver` | `kartoza/geoserver:latest` | 8080 | OGC WMS/WFS map tile server |

The custom PostGIS image compiles and installs from source:
- **PostGIS 3.4:** Geometry types, spatial indexes (`GIST`), and spatial relations.
- **pgvector v0.6.2:** High-dimensional vector embeddings and cosine/L2 search.
- **Apache AGE (PG16):** Graph database engine with Cypher query support.

---

## 📁 Project Structure

```
BOOTCAMPGIS_GEOAI/
├── .agents/
│   ├── AGENTS.md                   # Engineering standards, zero-trust rules & directives
│   ├── LOGS.md                     # Development journal and milestone records
│   └── BUGS.md                     # Root-cause analysis and bug tracker
├── .env                            # Local secrets and API keys (not committed)
├── .env.example                    # Environment variable template
├── pytest.ini                      # Pytest discovery configuration (pythonpath = .)
├── requirements.txt                # Pinned Python package dependencies
├── data/
│   └── complementary_lessons_materials/ # Course materials, prompts (Lessons 01 → 09) & geocoding cache
├── notebooks/
│   ├── KAGGLE_ETL_PIPELINE.ipynb   # Raw data ingestion, NLP embeddings & Kaggle ETL
│   └── kaggle_deploy/              # Dataset packaging and deployment utilities
├── scratch/                        # Cypher and SQL diagnostic test scripts
├── scripts/
│   └── geostack/
│       ├── docker-compose.yml      # Multi-container orchestration (db + geoserver)
│       └── postgis/
│           └── Dockerfile          # Custom PG16 + PostGIS + pgvector + Apache AGE build
├── src/
│   ├── agent/
│   │   ├── config.py               # Centralized pydantic-settings environment loading
│   │   ├── db_engine.py            # SQLAlchemy 2.x connection pooling + schema cache
│   │   ├── apply_db_metadata.py    # Census metadata loader & business_rules table seeder
│   │   ├── hotfix_gmap_spatial.py  # Spatial dimension pipeline (gmap_places)
│   │   ├── swarm_state.py          # SwarmState TypedDict schema
│   │   ├── swarm_graph.py          # StateGraph compilation & CLI execution harness
│   │   ├── agents/
│   │   │   ├── planner.py          # Planner agent with live schema injection
│   │   │   ├── worker.py           # Worker agent with ReAct execution loop
│   │   │   └── reviewer.py         # Reviewer critic with GIS validation sensor
│   │   └── tools/
│   │       ├── api_tools.py        # Routes API v2 tool
│   │       ├── spatial_tools.py    # PostGIS logistics & geomarketing tools
│   │       └── rag_tools.py        # pgvector & Apache AGE graph tools
│   └── frontend/
│       ├── app.py                  # Streamlit web dashboard (75/25 split layout)
│       └── map_utils.py            # Folium map builder (polygons, markers, popups)
└── tests/
    ├── unit/
    │   ├── test_api_tools.py       # Routes API v2 test cases
    │   ├── test_app_layout.py      # Streamlit layout configuration tests
    │   ├── test_app_state.py       # Session state memory tests
    │   ├── test_apply_db_metadata.py# Census metadata and context caching tests
    │   ├── test_db_engine.py       # Connection pool initialization tests
    │   ├── test_hotfix_gmap.py     # Geometry validation tests for POI dimension
    │   ├── test_map_utils.py       # Map rendering and feature collection tests
    │   ├── test_planner.py         # Planner structured output schema tests
    │   ├── test_rag_tools.py       # Vector search and Cypher graph tool tests
    │   ├── test_reviewer.py        # Critic schema and loop counting tests
    │   ├── test_spatial_tools.py   # PostGIS spatial functions tests
    │   ├── test_swarm_graph.py     # Graph edge routing & emergency brake tests
    │   └── test_worker.py          # Worker execution & feedback injection tests
    ├── integration/
    │   └── test_crud_workflow.py   # Spatial ORM CRUD & SQL injection validation
    └── test_swarm.py               # End-to-end swarm test harness
```

> [!NOTE]
> **Complementary Lessons & Prompts:** The [`data/complementary_lessons_materials/`](data/complementary_lessons_materials/) directory contains the complete archive of prompt engineering blueprints, class-by-class setup scripts, the pre-computed Google Maps geocoding cache (`.geocoding_cache.json`), and reference materials used to iteratively construct each layer of this GeoAI solution across Lessons 01 to 09.

---

## 🛠️ Database Engine & ORM

The project uses **SQLAlchemy 2.x** and **GeoAlchemy2** for robust, secure spatial database interactions.

- **Connection Pooling:** Managed via `src/agent/db_engine.py` with `pool_size=10`, `max_overflow=20`, `pool_pre_ping=True`, and `pool_recycle=3600` to prevent stale connection drops.
- **SQL Injection Prevention:** All spatial queries and ORM interactions use strict SQLAlchemy parameter binding (`:param`), completely eliminating SQL injection vulnerabilities.
- **Extension Initialization:** The `DBEngine.init_extensions()` method automatically activates `postgis`, `vector`, and `age` inside an `AUTOCOMMIT` isolation block (required by Apache AGE).
- **Cognitive Blueprint Schema Awareness:** Official Census metadata and column definitions (`COMMENT ON COLUMN`) are extracted from `pg_description` and cached once at module boot via `load_context_once()`, injecting schema awareness into agent prompts with zero DB overhead.
- **Spatial Dimension Table:** Places are relationally separated into `gmap_places` (EPSG:4326), joined to `gmap_reviews_enriched` on `gmap_id`.

---

## ⚙️ Configuration & Security

Configuration is loaded centrally via `pydantic-settings` (`BaseSettings`) from `.env`. **Hardcoded credentials in source code are strictly forbidden.**

Required and optional `.env` keys (see [`.env.example`](.env.example) for full template):

```env
# Google Cloud & Gemini AI
PROJECT_ID=your_gcp_project_id
GCP_API_KEY=your_google_cloud_api_key
GOOGLE_API_KEY=your_gemini_api_key
LLM_MODEL=gemini-2.0-flash
EMBEDDING_MODEL=BAAI/bge-large-en-v1.5

# Database & GeoServer
DATABASE_URL=postgresql://postgres:12345@localhost:5432/bootcampgis
DB_USER=postgres
DB_NAME=bootcampgis
DB_PASSWORD=your_password
GEOSERVER_ADMIN_PASS=your_geoserver_password

# LangSmith Tracing (Optional)
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=your_langsmith_api_key
LANGSMITH_PROJECT=GeoAI_Bootcamp

# External Data & Census FIPS (Optional / ETL)
CENSUS_API_KEY=your_census_api_key
CENSUS_YEAR=2023
TARGET_STATE=12
TARGET_COUNTY=057
TARGET_PLACE=71000
```

---

## 🚀 Getting Started

### 1. Virtual Environment Setup

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

### 3. Launch GeoStack (Docker)

Start the PostgreSQL / PostGIS / pgvector / Apache AGE container and GeoServer:

```bash
docker compose -f scripts/geostack/docker-compose.yml up -d --build
```

Verify service status:

```bash
docker compose -f scripts/geostack/docker-compose.yml ps
```

### 4. Initialize Database & Seed Metadata

```bash
# Run extension initialization and test connection
python -m src.agent.db_engine

# Inject column descriptions and business rules
python -m src.agent.apply_db_metadata
```

### 5. Run the Test Suite

Run unit and integration tests using Pytest:

```bash
# Run all unit tests
pytest tests/unit/

# Run spatial integration tests (requires Docker stack)
pytest tests/integration/
```

### 6. Run the Swarm CLI (Interactive REPL)

```bash
python -m src.agent.swarm_graph
```

### 7. Run the Geospatial Web Dashboard (Streamlit)

```bash
streamlit run src/frontend/app.py
```

---

## 🧪 Test Suite Summary

| Test Module | Suite | Verified Functionality |
|---|---|---|
| `test_api_tools.py` | Unit | Routes API v2 request/response parsing, HTTP error handling, missing keys |
| `test_app_layout.py` | Unit | Streamlit layout ratios (75/25), page config title, and CSS injection |
| `test_app_state.py` | Unit | Streamlit session memory initialization and reset controls |
| `test_apply_db_metadata.py` | Unit | Census metadata extraction, `pg_description` caching, single-hit DB behavior |
| `test_db_engine.py` | Unit | Connection pool initialization, parameters, and health checks |
| `test_hotfix_gmap.py` | Unit | Valid geometry formatting (`Point`), EPSG:4326 compliance for POIs |
| `test_map_utils.py` | Unit | Dynamic Folium layers, bounding box auto-centering, marker colors |
| `test_planner.py` | Unit | Pydantic `PlannerOutput` structured schema compliance |
| `test_rag_tools.py` | Unit | pgvector cosine query compilation and Apache AGE Cypher traversal syntax |
| `test_reviewer.py` | Unit | Critic output schema, retry feedback formatting, loop count increments |
| `test_spatial_tools.py` | Unit | Unit conversions, buffer calculations, and PostGIS SQL generation |
| `test_swarm_graph.py` | Unit | Conditional edge routing, max retry safety cutoff, emergency brake node |
| `test_worker.py` | Unit | ReAct tool loop, reviewer critique injection, final response synthesis |
| `test_crud_workflow.py` | Integration | End-to-end spatial ORM CRUD with parameter binding injection safety |
| `test_swarm.py` | End-to-End | Full Planner → Worker → Reviewer flow execution with mock LLM |

---

## 📚 Development Journal

See [`.agents/LOGS.md`](.agents/LOGS.md) for detailed chronological logs and [`.agents/BUGS.md`](.agents/BUGS.md) for root-cause analyses of solved issues.

### Completed Milestones

| Date | Milestone |
|---|---|
| 2026-08-24 | Hello World LangGraph Agent with conditional intent routing |
| 2026-08-24 | Standalone `get_route_distance_time` tool (Routes API v2) |
| 2026-08-25 | Core spatial & RAG tools implemented (`spatial_tools.py`, `rag_tools.py`) |
| 2026-08-25 | Swarm Planner Node with Pydantic structured output (`PlannerOutput`) |
| 2026-08-25 | Swarm Worker Node with internal ReAct tool loop and feedback handling |
| 2026-08-25 | Swarm Reviewer Node & compiled Actor-Critic graph with 3-retry safety cap |
| 2026-09-02 | Cognitive Blueprint: US Census metadata & schema context injection into LLM prompts |
| 2026-09-02 | Hotfix: Geocoded 5,108 Google Maps POIs into spatial dimension table `gmap_places` |
| 2026-09-06 | Super Prompt v6: Dynamic spatial bounding, deterministic Py math, Folium UI integration |
| 2026-10-12 | Lesson 9 System Integration: High-performance ingestion with GIN indexes, Cypher UNWIND, `submit_final_response` tool, and teleprompter alignment |

---

## 👨‍💻 Author & Lead Architect

**Dr. Atilio Efrain Bica Grondona**  
*Principal AI Architect, GeoAI Tech Lead & BootcampGIS Instructor*  
Ph.D. in Remote Sensing (UFRGS) | Dual Citizen (Brazil & Italy / EU)

With over 10 years of experience bridging deep scientific Earth Observation (EO), applied mathematics, and enterprise-grade generative AI, Dr. Grondona specializes in designing nested agentic architectures (LangGraph, MCP), physics-informed neural modeling, and spatial intelligence platforms (PostGIS, pgvector, Apache AGE).

- 🔗 **LinkedIn:** [linkedin.com/in/atilio-grondona-ph-d-6b42a22b](https://www.linkedin.com/in/atilio-grondona-ph-d-6b42a22b/)
- 🎓 **Google Scholar:** [Atilio Grondona on Google Scholar](https://scholar.google.com/citations?user=ijZpuvMAAAAJ&hl=en)
- 🐙 **GitHub:** [github.com/atilioebg](https://github.com/atilioebg)

---

## 📄 License & Terms of Use

### 1. Educational & Academic Use
This repository and its associated course materials were developed for the **BootcampGIS GeoAI Curriculum**. Enrolled BootcampGIS students, educators, and academic researchers are granted permission to:
- Clone, run, and experiment with the codebase locally for educational purposes.
- Adapt code patterns for personal academic research, non-commercial projects, and personal portfolio showcases (with proper attribution to the author and BootcampGIS).

### 2. Commercial Restrictions & Intellectual Property
- **Proprietary Courseware:** The instructional course structure, video teleprompter materials, and prompt blueprints in [`data/complementary_lessons_materials/`](data/complementary_lessons_materials/) are the intellectual property of **Dr. Atilio Grondona** and **BootcampGIS**.
- **No Resale or Sublicensing:** Direct redistribution, re-packaging, re-branding, or commercial resale of this curriculum, whether as online courses, bootcamps, workshops, or commercial educational products, is strictly prohibited without prior written consent from BootcampGIS and the author.

### 3. Disclaimer & Limitation of Liability
- **As-Is Basis:** This software and its analytical tools are provided "as-is" for educational and demonstrative purposes, without warranty of any kind.
- **Decision-Making:** The site selection recommendations generated by the agent swarm represent algorithmic models and should not replace professional geospatial, financial, or commercial real estate analysis.
- **Third-Party API Costs:** Users are solely responsible for managing their own API credentials and cloud infrastructure costs (Google Cloud / Routes API, Gemini, LangSmith, GeoServer, and PostGIS). Neither the author nor BootcampGIS accepts liability for cloud billing expenses incurred during usage.
