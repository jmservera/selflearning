# Project Context

- **Owner:** jmservera
- **Project:** Self-learning AI system — scrapes the internet for knowledge on a given topic and becomes a PhD-level expert. Self-healing and self-improving.
- **Stack:** Python 3.12+ with FastAPI, Azure AI Foundry, Cosmos DB, Azure Service Bus, Container Apps
- **Created:** 2026-03-12

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->

### 2026-03-12: Team formation
- Responsible for: testing, quality assurance, self-evaluation loops, improvement metrics
- Team: Morpheus (Lead), Trinity (Data), Oracle (AI/ML), Tank (Backend), Niobe (Tester — me)
- I validate everything: scraped data quality, knowledge accuracy, pipeline integrity, self-improvement metrics

### 2026-03-12: System Architecture (Morpheus)
- **8 services:** Scraper, Extractor, Knowledge, Reasoner, Evaluator, Orchestrator, Healer, API Gateway
- **Messaging:** Azure Service Bus (queues + pub/sub topics) for inter-service communication
- **Storage:** Cosmos DB NoSQL for knowledge graph (serverless), Azure AI Search for vector search
- **Compute:** Azure Container Apps with KEDA auto-scaling
- **AI:** Serverless model deployments in Azure AI Foundry (GPT-4o, GPT-4o-mini, text-embedding-3-large)
- **IaC:** Bicep with managed identity for authentication (no API keys)
- **Resilience:** Three-layer self-healing (infrastructure auto-restart, pipeline DLQ recovery, cognitive learning adjustment)
- **My role:** Evaluator service assesses knowledge quality and accuracy, Healer service implements cognitive learning loops (prompt tuning, strategy adjustment, knowledge refresh), testing framework validates pipeline integrity and self-improvement metrics

### 2026-03-12: Evaluator Service & Test Infrastructure Implementation
- Built complete evaluator service (8 files in src/evaluator/): config, models, knowledge_client, service_bus, question_generator, evaluation engine, FastAPI app
- Evaluation pipeline: taxonomy coverage → self-test (LLM questions + RAG answers) → confidence analysis → gap detection → scoring (0-100 with weighted subscores)
- Test infrastructure covers 5 services with 160 tests (159 pass, 1 skipped for optional dep)
- Test approach: evaluator tests against real service; other service tests use inline reference implementations as executable behavioral specs (TDD-first: tests from requirements, not implementation)
- Key patterns: mock Azure clients in conftest.py, respx for HTTP mocking, pytest-asyncio for async tests, sample data fixtures shared across test files
- Scoring formula: overall = coverage(25%) + depth(20%) + accuracy(35%) + recency(20%)
- Gap severities: critical (0 entities), moderate (thin coverage or low confidence), minor (missing relationships)

