# Project Context

- **Owner:** jmservera
- **Project:** Self-learning AI system — scrapes the internet for knowledge on a given topic and becomes a PhD-level expert. Self-healing and self-improving.
- **Stack:** Python 3.12+ with FastAPI, Azure AI Foundry, Cosmos DB, Azure Service Bus, Container Apps
- **Created:** 2026-03-12

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->

### 2026-03-12: Team formation
- Responsible for: web scraping, crawling infrastructure, data pipelines, content extraction
- Team: Morpheus (Lead), Trinity (Data — me), Oracle (AI/ML), Tank (Backend), Niobe (Tester)
- Data flows from my scrapers → Oracle's extraction → Tank's storage

### 2026-03-12: System Architecture (Morpheus)
- **8 services:** Scraper, Extractor, Knowledge, Reasoner, Evaluator, Orchestrator, Healer, API Gateway
- **Messaging:** Azure Service Bus (queues + pub/sub topics) for inter-service communication
- **Storage:** Cosmos DB NoSQL for knowledge graph (serverless), Azure AI Search for vector search
- **Compute:** Azure Container Apps with KEDA auto-scaling
- **AI:** Serverless model deployments in Azure AI Foundry (GPT-4o, GPT-4o-mini, text-embedding-3-large)
- **IaC:** Bicep with managed identity for authentication (no API keys)
- **Resilience:** Three-layer self-healing (infrastructure auto-restart, pipeline DLQ recovery, cognitive learning adjustment)
- **My role:** Scraper service ingests raw web content → Extractor (Oracle) cleans and structures data → Knowledge/Reasoner/Evaluator (Oracle) extract insights → API/Storage (Tank) persist to Cosmos DB

### 2026-03-12: Scraper Service Implementation
- **Files:** `src/scraper/` — `main.py`, `config.py`, `models.py`, `scraper.py`, `service_bus.py`, `storage.py`
- **Pattern:** FastAPI lifespan manages all async clients (credential, blob, cosmos, service bus)
- **Config:** Pydantic Settings with `SCRAPER_` env prefix — all Azure endpoints are env vars
- **Auth:** `DefaultAzureCredential` (async) shared across all Azure SDK clients
- **Message contracts:** `ScrapeRequest` in from `scrape-requests` queue → `ScrapeCompleteEvent` out to `scrape-complete` topic
- **Dedup:** Two-layer — URL recency check + content SHA-256 hash check, both via Cosmos DB
- **Rate limiting:** Token-bucket per domain, configurable rate/burst
- **Robots.txt:** Cached per domain, fetched lazily, permissive on errors
- **Content extraction:** BeautifulSoup strips nav/ads/scripts/aside, prefers `<main>`/`<article>` tags
- **Blob path convention:** `{topic}/{domain}/{hash_prefix}.html`
- **Cosmos partition key:** domain (keeps URL dedup queries local)
- **Dead-letter:** Service Bus SDK handles retries; manual DLQ on deserialization errors or max delivery count
- **Dependency added:** `pydantic-settings>=2.7.0` to `requirements.txt`
- **Telemetry:** OpenTelemetry spans on all major operations; Azure Monitor configured when connection string present

### 2026-03-12: Five-agent parallel spawn complete
- Oracle (Extractor + Reasoner), Tank (Knowledge + API Gateway), Niobe (Evaluator + Tests), Morpheus (Orchestrator + Healer) all completed and committed
- **Total deliverables:** 61 Python source files, ~12,634 LOC production code, ~2,910 LOC test code
- **Test results:** 159 passing, 1 skipped across all test suites
- **Cross-team decisions merged:** 6 decision documents consolidated into `.squad/decisions.md`, inbox cleared
- **Design patterns established:** All services follow pydantic-settings config, FastAPI with lifespan, OpenTelemetry instrumentation, graceful degradation on startup
- **Integration ready:** All services coordinate via Service Bus (queues + pub/sub topics), Cosmos DB (partition key = topic), Azure AI Search (hybrid search)
- **Next iteration:** Integration testing, first learning loop (scrape → extract → organize → reason → evaluate → improve), production deployment prep

