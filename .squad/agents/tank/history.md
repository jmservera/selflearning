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

