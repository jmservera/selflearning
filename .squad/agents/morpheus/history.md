# Project Context

- **Owner:** jmservera
- **Project:** Self-learning AI system — scrapes the internet for knowledge on a given topic and becomes a PhD-level expert. Self-healing and self-improving.
- **Stack:** Python 3.12+, FastAPI, Azure AI Foundry, Azure Container Apps, Cosmos DB, Service Bus, AI Search
- **Created:** 2026-03-12

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->

### 2026-03-12: Team formation
- Team assembled: Morpheus (Lead), Trinity (Data), Oracle (AI/ML), Tank (Backend), Niobe (Tester)
- Core mission: build a self-improving AI that scrapes the internet and synthesizes PhD-level expertise
- Key subsystems: web scraping → knowledge extraction → knowledge graph → self-evaluation → improvement loop

### 2026-03-12: System architecture designed and scaffolded
- **Architecture doc:** `docs/architecture.md` — 11 sections covering all components, Azure services, data model, deployment
- **8 services:** Scraper, Extractor, Knowledge, Reasoner, Evaluator, Orchestrator, Healer, API Gateway
- **Key decisions:**
  - Cosmos DB NoSQL (not Graph API) for knowledge storage — better vector search, serverless tier
  - Azure AI Search for vector indexing — hybrid search superior to Cosmos-native vectors for RAG
  - Service Bus queues + topics for all inter-service communication — DLQ critical for self-healing
  - Serverless AI model deployments (pay-per-token) — no GPU reservation for bursty workloads
  - Bicep IaC with azd — native Azure, no Terraform state management
  - Single managed identity with RBAC — no API keys in code
  - Three-layer self-healing: infrastructure (Azure-native), pipeline (Healer DLQ/circuit-break), cognitive (prompt tuning/strategy adjustment)
- **Owner preferences:** jmservera wants Azure AI Foundry (Microsoft Foundry), Container Apps, azd deployment
- **Project structure:** `infra/` (Bicep modules), `src/` (8 service dirs), `docs/`, `tests/`
- **Decision record:** `.squad/decisions/inbox/morpheus-system-architecture.md`
- **Partition strategy:** Cosmos DB partitioned by `topic` — co-locates all knowledge for efficient graph traversal
- **Models:** GPT-4o (reasoning/extraction), GPT-4o-mini (lightweight tasks), text-embedding-3-large (embeddings)
