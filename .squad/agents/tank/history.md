# Project Context

- **Owner:** jmservera
- **Project:** Self-learning AI system — scrapes the internet for knowledge on a given topic and becomes a PhD-level expert. Self-healing and self-improving.
- **Stack:** Python 3.12+ with FastAPI, Azure AI Foundry, Cosmos DB, Azure Service Bus, Container Apps
- **Created:** 2026-03-12

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->

### 2026-03-12: Team formation
- Responsible for: APIs, storage, knowledge graph infrastructure, backend services
- Team: Morpheus (Lead), Trinity (Data), Oracle (AI/ML), Tank (Backend — me), Niobe (Tester)
- I provide the storage and API backbone — knowledge graph, data models, service infrastructure

### 2026-03-12: System Architecture (Morpheus)
- **8 services:** Scraper, Extractor, Knowledge, Reasoner, Evaluator, Orchestrator, Healer, API Gateway
- **Messaging:** Azure Service Bus (queues + pub/sub topics) for inter-service communication
- **Storage:** Cosmos DB NoSQL for knowledge graph (serverless), Azure AI Search for vector search
- **Compute:** Azure Container Apps with KEDA auto-scaling
- **AI:** Serverless model deployments in Azure AI Foundry (GPT-4o, GPT-4o-mini, text-embedding-3-large)
- **IaC:** Bicep with managed identity for authentication (no API keys)
- **Resilience:** Three-layer self-healing (infrastructure auto-restart, pipeline DLQ recovery, cognitive learning adjustment)
- **My role:** Orchestrator service coordinates all services, API Gateway exposes REST/async endpoints, storage layer persists to Cosmos DB, AI Search indexes knowledge for RAG, Healer monitors and recovers from failures

### 2026-03-12: Knowledge Service + API Gateway implementation
- **Knowledge Service** (src/knowledge/) — 7 Python files, ~3k lines total
  - Cosmos DB async CRUD with entity resolution (name+alias fuzzy matching, field merge)
  - Azure AI Search hybrid search (vector + keyword + faceted)
  - Service Bus consumer: extraction-complete → ingest → re-index
  - Bulk ingest pipeline, topic stats/summary analytics
  - Partition key: `topic` — all queries are partition-aware
- **API Gateway** (src/api/) — 9 Python files
  - External HTTP API: topic CRUD, learning control, knowledge search, dashboard
  - RAG chat: search knowledge graph → build context → call GPT-4o → return with citations
  - WebSocket handlers for live status + log streaming
  - Graceful degradation: falls back to Service Bus queuing when orchestrator is unreachable
  - CORS middleware for web UI consumption
- **Design decisions:**
  - One AI Search index per topic (dynamic creation via ensure_index)
  - Entity resolution uses SequenceMatcher > 0.85 threshold + alias set intersection
  - Chat confidence is estimated from citation quality + source count − uncertainty phrases
  - All Azure auth via DefaultAzureCredential (managed identity)
  - OpenTelemetry spans on every operation

### 2026-03-12: Five-agent parallel spawn complete
- Trinity (Scraper), Oracle (Extractor + Reasoner), Niobe (Evaluator + Tests), Morpheus (Orchestrator + Healer) all completed and committed
- **Total deliverables:** 61 Python source files, ~12,634 LOC production code, ~2,910 LOC test code
- **Test results:** 159 passing, 1 skipped across all test suites
- **Cross-team decisions merged:** 6 decision documents consolidated into `.squad/decisions.md`, inbox cleared
- **Design patterns established:** All services follow pydantic-settings config, FastAPI with lifespan, OpenTelemetry instrumentation, graceful degradation on startup
- **Integration ready:** All services coordinate via Service Bus (queues + pub/sub topics), Cosmos DB (partition key = topic), Azure AI Search (hybrid search)
- **Incoming dependencies:** Extractor/Reasoner feed entities/insights to Knowledge service; Evaluator queries Knowledge endpoints; Orchestrator manages all through Service Bus
- **Next iteration:** Integration testing, first learning loop (scrape → extract → organize → reason → evaluate → improve), production deployment prep

### 2026-03-12: Control UI React application
- **Built complete frontend:** Vite + React + TypeScript SPA in src/ui/ with 42 files, ~7,864 LOC
- **Project structure:**
  - TypeScript types mirroring all Python API models (TopicResponse, SearchResponse, ChatResponse, etc.)
  - API client with fetch-based calls to all backend endpoints
  - WebSocket hooks for real-time status and log streaming with auto-reconnect
  - Layout system with collapsible sidebar, header with system status
  - Dashboard page with 5 panels: StatusPanel (live metrics), ProgressChart (topic cards), ActivityLog (streaming feed), SteeringControls (topic creation form)
- **Design patterns:**
  - Dark mode by default (Tailwind slate-900/950 backgrounds, blue/emerald/amber/rose accents)
  - Custom hooks: useDashboard (auto-refresh every 5s), useTopics (CRUD operations), useWebSocket (auto-reconnect with exponential backoff)
  - TopicCard shows status badge, progress bar, priority dots, entity/claim counts, inline controls (start/pause/resume, priority up/down)
  - ActivityLog shows emoji icons per service, success/fail indicators, auto-scrolls to new entries
  - SteeringControls has collapsible form with sliders for priority (1-10) and target expertise (0-1)
- **Integration with Oracle:**
  - ChatPage and KnowledgeExplorerPage built by Oracle, integrated via lazy loading with fallback placeholders
  - Fixed API calls in both pages (api.topics.list, api.chat.send, api.knowledge.search, api.knowledge.getEntity)
  - Shared Entity type extended with optional relationships and claims arrays
- **Deployment:**
  - Multi-stage Dockerfile: node:20-alpine build → nginx:alpine serve
  - nginx.conf with SPA fallback, API proxy to /api/*, WebSocket proxy to /ws/*
  - Added ui service to azure.yaml (language: js, host: containerapp)
- **Build verified:** npm install + npm run build succeeded, no errors
- **Code review (Morpheus):** APPROVED WITH NOTES — Type alignment fixed, architecture consistent, deployment ready
- **Cross-agent awareness:** Oracle's Chat/Knowledge Explorer components use Tank's API client and type definitions. All frontend API calls use namespaced endpoints (api.chat.send, api.knowledge.search, etc.). Tank maintains type sync with backend — Oracle's components never drift from contracts.


### 2026-03-13: PR reviews round 2 (PRs #13-16) — Docker Compose review & emulator auth blocker
- **PR #13 (Reasoner HTTP endpoints):** APPROVED. 382 tests pass. Added GET /status, POST /reason, GET /results endpoints. Pattern for future services.
- **PR #14 (API Gateway tests):** APPROVED. 35 tests, 100% endpoint coverage. Ready for production.
- **PR #15 (Cosmos DB migration):** APPROVED. Graceful fallback pattern — in-memory stores as safety net during external persistence failures. Useful for Reasoner/Healer; not for Knowledge/Orchestrator/Scraper (fail-closed required).
- **PR #16 (Docker compose):** CHANGES_REQUESTED. Identified critical blocker: local emulator authentication missing. All services default to DefaultAzureCredential (production managed identity) but Cosmos DB emulator + Azurite require well-known account keys. Affects Knowledge, Scraper, Orchestrator, Extractor services.
  - **Solution documented:** Conditional auth pattern — detect emulator endpoints, use well-known keys; otherwise use DefaultAzureCredential
  - **Implementation required:** Cosmos DB (localhost:8081, cosmos:8081) and Azurite (localhost:10000, devstoreaccount1) conditional auth in storage modules
  - **Team assignments:** Trinity (Scraper auth fix), Oracle (Extractor auth fix), Morpheus (Orchestrator auth fix)
  - **Blocker severity:** HIGH — prevents local testing of full pipeline until resolved
- **Decisions merged:** 3 new patterns to .squad/decisions.md (Graceful Fallback, Reasoner HTTP Endpoints, Emulator Authentication)
- **Next:** Re-review PR #16 after auth fixes implemented and verified
