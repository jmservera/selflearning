# Project Context

- **Owner:** jmservera
- **Project:** Self-learning AI system — scrapes the internet for knowledge on a given topic and becomes a PhD-level expert. Self-healing and self-improving.
- **Stack:** Python 3.12+ with FastAPI, Azure AI Foundry, Cosmos DB, Azure Service Bus, Container Apps
- **Created:** 2026-03-12

## Learnings

<!-- Append new learnings below. Each entry is something lasting about the project. -->

### 2026-03-12: Team formation
- Responsible for: LLM integration, knowledge extraction, reasoning chains, self-improvement loops
- Team: Morpheus (Lead), Trinity (Data), Oracle (AI/ML — me), Tank (Backend), Niobe (Tester)
- I consume clean data from Trinity, extract knowledge, and feed it to Tank's storage layer

### 2026-03-12: System Architecture (Morpheus)
- **8 services:** Scraper, Extractor, Knowledge, Reasoner, Evaluator, Orchestrator, Healer, API Gateway
- **Messaging:** Azure Service Bus (queues + pub/sub topics) for inter-service communication
- **Storage:** Cosmos DB NoSQL for knowledge graph (serverless), Azure AI Search for vector search
- **Compute:** Azure Container Apps with KEDA auto-scaling
- **AI:** Serverless model deployments in Azure AI Foundry (GPT-4o, GPT-4o-mini, text-embedding-3-large)
- **IaC:** Bicep with managed identity for authentication (no API keys)
- **Resilience:** Three-layer self-healing (infrastructure auto-restart, pipeline DLQ recovery, cognitive learning adjustment)
- **My role:** Extractor (receive from Trinity's Scraper) → Knowledge/Reasoner/Evaluator services (my domain) → Orchestrator coordinates reasoning chains and learning loops → Healer adjusts strategies

### 2026-03-12: Extractor & Reasoner Implementation
- Implemented both services as first real Python code in the project (2,590 LOC across 15 files)
- **Extractor pattern**: chunk → extract entities → extract relationships → extract claims → summarize → embed
- **Reasoner strategies**: gap_analysis, contradiction_resolution, synthesis, depth_probe
- Established service patterns for the team: pydantic-settings config, LLMClient wrapper, ServiceBusHandler consume loop, FastAPI lifespan lifecycle
- LLM client is model-agnostic — model name is a config parameter, same client swaps between GPT-4o/mini
- All LLM calls instrumented with OpenTelemetry spans recording model, tokens, latency
- JSON mode (`response_format={"type": "json_object"}`) used for structured extraction; markdown code-fence stripping handles edge cases
- Entity deduplication uses case-insensitive name normalization, keeps highest-confidence version
- Document chunking prefers paragraph boundaries, then sentence boundaries, with configurable overlap
- Prompts include few-shot examples, confidence scoring instructions, and empty-content edge-case handling
- Reasoner uses RAG pattern: retrieve from Knowledge service via HTTP → augment prompt → LLM reasoning
- Added pydantic-settings to both requirements.txt files

