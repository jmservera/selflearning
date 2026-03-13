# selflearning — System Architecture

> A self-learning AI system that scrapes the internet, synthesizes PhD-level expertise on any topic, and continuously self-heals and self-improves.

---

## 1. System Overview

**selflearning** is an autonomous knowledge-acquisition platform. Given a topic, it:

1. **Discovers** relevant sources across the internet
2. **Extracts** structured knowledge from unstructured content
3. **Organizes** knowledge into a graph with relationships and hierarchies
4. **Reasons** over accumulated knowledge to fill gaps and synthesize insights
5. **Evaluates** its own expertise against benchmarks and known authorities
6. **Improves** by identifying weaknesses and scheduling targeted learning

The system runs entirely on Azure, orchestrated through Azure Container Apps, with Azure AI Foundry (Microsoft Foundry) providing all AI/ML capabilities. Deployment is fully automated via `azd up`.

### Core Design Principles

| Principle | Implementation |
|---|---|
| **Composable** | Each service is an independent Container App with its own scaling rules |
| **Event-driven** | Services communicate via Azure Service Bus queues and topics |
| **Observable** | Azure Monitor + Application Insights across all services |
| **Cost-conscious** | Scale-to-zero on all Container Apps; consumption-tier Service Bus |
| **Python-first** | All AI/ML services in Python; flexibility for Go/Rust where performance matters |
| **Self-healing** | Dedicated healer service monitors, detects failures, and triggers recovery |

---

## 2. Component Architecture

The system is composed of **8 services**, each deployed as an Azure Container App:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        selflearning system                         │
│                                                                     │
│  ┌───────────┐    ┌───────────┐    ┌────────────┐                  │
│  │  Scraper   │───▶│ Extractor │───▶│ Knowledge  │                  │
│  │  Service   │    │  Service  │    │  Service   │                  │
│  └───────────┘    └───────────┘    └────────────┘                  │
│       │                                   │                         │
│       │           ┌───────────┐           │                         │
│       │           │  Reasoner │◀──────────┘                         │
│       │           │  Service  │                                     │
│       │           └─────┬─────┘                                     │
│       │                 │                                           │
│       │           ┌─────▼─────┐    ┌────────────┐                  │
│       │           │ Evaluator │───▶│Orchestrator│                  │
│       │           │  Service  │    │  Service   │                  │
│       │           └───────────┘    └──────┬─────┘                  │
│       │                                    │                        │
│       ◀────────────────────────────────────┘                        │
│                                                                     │
│  ┌───────────┐    ┌───────────┐                                    │
│  │  Healer   │    │    API    │                                    │
│  │  Service  │    │  Gateway  │                                    │
│  └───────────┘    └───────────┘                                    │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.1 Scraper Service (`src/scraper`)

**Purpose:** Discovers and retrieves content from the internet.

- **Inputs:** Topic queries, URL seeds, discovery instructions (via Service Bus queue `scrape-requests`)
- **Outputs:** Raw content documents (HTML, PDF text, API responses) written to Azure Blob Storage; completion events to `scrape-complete` topic
- **Scaling:** KEDA-driven from `scrape-requests` queue depth
- **Key behaviors:**
  - Respects robots.txt and rate limits
  - Deduplicates URLs against Cosmos DB crawl history
  - Supports pluggable source adapters (web, academic APIs, RSS, social)
  - Stores raw content in Blob Storage with metadata (URL, timestamp, content hash)

### 2.2 Extractor Service (`src/extractor`)

**Purpose:** Transforms raw content into structured knowledge units.

- **Inputs:** Raw content references from `scrape-complete` topic
- **Outputs:** Structured knowledge units (entities, relationships, claims, summaries) to `extraction-complete` topic
- **AI Foundry usage:**
  - LLM calls for entity extraction, relationship identification, claim extraction
  - Embedding generation for semantic similarity
- **Key behaviors:**
  - Produces typed knowledge units: `Entity`, `Relationship`, `Claim`, `Summary`
  - Each unit carries provenance (source URL, extraction confidence, timestamp)
  - Chunking strategy for long documents with overlap

### 2.3 Knowledge Service (`src/knowledge`)

**Purpose:** Manages the knowledge graph — the system's accumulated expertise.

- **Inputs:** Structured knowledge units from `extraction-complete` topic
- **Outputs:** Knowledge graph mutations; serves queries via internal API
- **Storage:** Azure Cosmos DB (NoSQL API with vector search)
- **Key behaviors:**
  - Merges new knowledge with existing graph (entity resolution, relationship deduplication)
  - Maintains vector embeddings for semantic search
  - Tracks knowledge provenance and confidence scores
  - Exposes graph query API for other services
  - Detects contradictions between knowledge units

### 2.4 Reasoner Service (`src/reasoner`)

**Purpose:** Synthesizes knowledge, identifies gaps, generates insights.

- **Inputs:** Triggered by `reasoning-requests` queue; reads from Knowledge Service API
- **Outputs:** Synthesized insights, identified gaps, contradiction resolutions → `reasoning-complete` topic
- **AI Foundry usage:**
  - Multi-step reasoning chains via LLM (chain-of-thought, tree-of-thought)
  - RAG over the knowledge graph for grounded reasoning
- **Key behaviors:**
  - Gap analysis: identifies topics with thin coverage or low confidence
  - Contradiction resolution: weighs conflicting claims by source authority and recency
  - Insight synthesis: generates higher-order conclusions from atomic knowledge
  - Produces structured gap reports consumed by Orchestrator

### 2.5 Evaluator Service (`src/evaluator`)

**Purpose:** Measures the system's expertise level and identifies weaknesses.

- **Inputs:** Triggered on schedule and after reasoning cycles; reads from Knowledge Service
- **Outputs:** Expertise scorecards, gap reports → `evaluation-complete` topic
- **AI Foundry usage:**
  - LLM-as-judge for quality assessment
  - Embedding similarity for coverage analysis
- **Key behaviors:**
  - Generates benchmark questions and self-tests
  - Compares knowledge graph against authoritative taxonomies
  - Produces expertise scorecards: coverage %, confidence distribution, gap inventory
  - Tracks expertise trajectory over time

### 2.6 Orchestrator Service (`src/orchestrator`)

**Purpose:** Drives the learning pipeline — decides what to learn next.

- **Inputs:** Evaluation reports from `evaluation-complete`; user-initiated topic requests via API
- **Outputs:** Scrape requests, reasoning requests, learning plans
- **Key behaviors:**
  - Implements the **learning loop**: Evaluate → Plan → Scrape → Extract → Organize → Reason → Evaluate
  - Prioritizes learning actions based on gap severity and topic importance
  - Manages concurrent learning across multiple topics
  - Implements backoff and circuit-breaking for failing pipelines
  - Exposes learning status and progress via API

### 2.7 Healer Service (`src/healer`)

**Purpose:** Monitors system health, detects failures, triggers recovery.

- **Inputs:** Azure Monitor metrics, Application Insights traces, Service Bus dead-letter queues
- **Outputs:** Recovery actions (restart services, replay messages, adjust configurations)
- **Key behaviors:**
  - **Failure detection:** Monitors dead-letter queues, error rates, latency anomalies
  - **Self-healing actions:**
    - Replays failed messages from dead-letter queues
    - Triggers Container App revision restarts
    - Adjusts scaling rules based on load patterns
    - Re-routes around degraded AI Foundry endpoints
  - **Self-improvement:**
    - Analyzes failure patterns to suggest pipeline improvements
    - Tunes extraction prompts based on quality metrics
    - Adjusts scraping strategies based on success rates
  - Reports health status to API Gateway

### 2.8 API Gateway (`src/api`)

**Purpose:** External interface for users and integrations.

- **Inputs:** HTTP requests from users/clients
- **Outputs:** JSON API responses; commands to Orchestrator
- **Key behaviors:**
  - Topic management: create, configure, prioritize learning topics
  - Knowledge query: search and browse the knowledge graph
  - Expertise dashboard: view scorecards, learning progress, system health
  - Learning control: pause, resume, adjust learning strategies
  - Authentication via Microsoft Entra ID (Azure AD) *(planned — not yet implemented)*

---

## 3. Azure Services Map

| Component | Azure Service | SKU / Tier | Purpose |
|---|---|---|---|
| **AI/ML** | Azure AI Foundry (Account + Project) | Standard | LLM inference, embeddings, AI agents |
| **Compute** | Azure Container Apps | Consumption | All 8 microservices |
| **Container Apps Environment** | Container Apps Environment | Consumption | Shared environment for all apps |
| **Container Registry** | Azure Container Registry | Basic | Docker image storage |
| **Messaging** | Azure Service Bus | Standard | Event-driven communication between services |
| **Knowledge Store** | Azure Cosmos DB (NoSQL) | Serverless | Knowledge graph, crawl history, metadata |
| **Vector Search** | Azure AI Search | Basic | Vector index for semantic search over knowledge |
| **Raw Storage** | Azure Storage Account | Standard LRS | Blob storage for raw scraped content |
| **Secrets** | Azure Key Vault | Standard | API keys, connection strings, certificates |
| **Monitoring** | Azure Monitor + Application Insights | Pay-as-you-go | Observability across all services |
| **Log Analytics** | Log Analytics Workspace | Pay-as-you-go | Centralized logging |
| **Identity** | Managed Identity (System-assigned) | — | Service-to-service auth, no secrets in code |

### AI Foundry Configuration

The AI Foundry project deploys with the following model endpoints:

| Model | Purpose | Deployment Type |
|---|---|---|
| GPT-4o | Extraction, reasoning, evaluation | Serverless API (pay-per-token) |
| GPT-4o-mini | Lightweight extraction, classification | Serverless API (pay-per-token) |
| text-embedding-3-large | Knowledge embeddings, similarity | Serverless API (pay-per-token) |

All model access uses the Azure AI Foundry SDK (`azure-ai-projects`, `azure-ai-inference`) with managed identity authentication — no API keys in application code.

---

## 4. Learning Pipeline

The learning pipeline is the heart of the system. It operates as a continuous loop:

```
                    ┌──────────────────────┐
                    │   1. ORCHESTRATE     │
                    │   Plan what to learn │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │   2. SCRAPE          │
                    │   Discover & fetch   │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │   3. EXTRACT         │
                    │   Structure content  │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │   4. ORGANIZE        │
                    │   Merge into graph   │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │   5. REASON          │
                    │   Synthesize & fill  │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │   6. EVALUATE        │
                    │   Measure expertise  │
                    └──────────┬───────────┘
                               │
                    └───────────────────────┘
                         (back to 1)
```

### Stage Details

#### Stage 1: Orchestrate
- **Service:** Orchestrator
- **Input:** Evaluation reports, user topic requests
- **Output:** Learning plan (prioritized list of scrape targets, reasoning tasks)
- **Logic:** Examines gap reports, identifies highest-priority knowledge gaps, generates targeted search queries, creates scrape requests

#### Stage 2: Scrape
- **Service:** Scraper
- **Input:** Scrape requests (queries, URLs, source types)
- **Output:** Raw content in Blob Storage + metadata events
- **Logic:** Executes web searches, fetches pages, extracts text from PDFs, polls academic APIs

#### Stage 3: Extract
- **Service:** Extractor
- **Input:** Raw content references
- **Output:** Structured knowledge units (entities, relationships, claims)
- **Logic:** Uses AI Foundry LLMs to parse content, extract entities, identify relationships, assess claim confidence

#### Stage 4: Organize
- **Service:** Knowledge Service
- **Input:** Knowledge units
- **Output:** Updated knowledge graph in Cosmos DB + vector index in AI Search
- **Logic:** Entity resolution, deduplication, confidence scoring, contradiction detection, embedding generation

#### Stage 5: Reason
- **Service:** Reasoner
- **Input:** Knowledge graph subsets, gap reports
- **Output:** Synthesized insights, resolved contradictions, new gap reports
- **Logic:** Multi-hop reasoning over graph, RAG-grounded synthesis, gap identification

#### Stage 6: Evaluate
- **Service:** Evaluator
- **Input:** Knowledge graph, previous scorecards
- **Output:** Expertise scorecards, gap inventory, learning recommendations
- **Logic:** Self-generated Q&A tests, coverage analysis, confidence distribution, trajectory tracking

### Self-Evaluation Strategy

The Evaluator uses three complementary approaches:

1. **Taxonomy coverage:** Compare knowledge graph entities against known topic taxonomies (e.g., for "quantum computing": compare against ACM CCS categories). Coverage % indicates breadth.

2. **Self-testing:** Generate PhD-qualifying-exam-style questions using the LLM, then attempt to answer them using only the knowledge graph (RAG). Score answers for correctness and completeness.

3. **Authority comparison:** For key claims, compare against known authoritative sources. Track agreement rate as a confidence metric.

### Self-Improvement Strategy

The Orchestrator implements improvement through:

1. **Gap-driven learning:** Evaluation gaps directly become scrape targets (highest priority).
2. **Confidence boosting:** Low-confidence claims trigger targeted verification scraping.
3. **Prompt evolution:** The Healer analyzes extraction quality metrics and adjusts extraction prompts.
4. **Source diversification:** If knowledge relies on too few sources, the Orchestrator diversifies scrape targets.
5. **Depth escalation:** Once breadth coverage exceeds threshold, shift to depth — follow citations, find primary sources.

---

## 5. Self-Healing Architecture

Self-healing operates at three layers:

### Layer 1: Infrastructure Healing (Azure-native)
- Container Apps auto-restarts failed containers (health probes)
- KEDA scales services based on queue depth (handles load spikes)
- Service Bus dead-letter queues capture failed messages (no data loss)

### Layer 2: Pipeline Healing (Healer Service)
- **Dead-letter processing:** Healer monitors DLQ across all queues; analyzes failure reasons; replays recoverable messages with backoff
- **Circuit breaking:** If a service error rate exceeds threshold, Orchestrator pauses that pipeline stage and alerts Healer
- **Endpoint failover:** If an AI Foundry model endpoint is degraded, Healer switches to backup model deployment
- **Stale detection:** Healer detects when pipeline stages haven't processed messages within SLA and triggers investigation

### Layer 3: Cognitive Healing (Self-Improvement)
- **Extraction quality regression:** Healer monitors extraction confidence scores; if they drop, it triggers prompt review and adjustment
- **Knowledge decay:** Evaluator detects when knowledge becomes stale (old sources, outdated claims); Orchestrator schedules refresh scraping
- **Learning stagnation:** If expertise scores plateau, Orchestrator adjusts strategy — new source types, different search queries, deeper reasoning chains

### Health Monitoring Flow

```
All Services ──metrics/logs──▶ Application Insights
                                      │
                                      ▼
                              Azure Monitor Alerts
                                      │
                                      ▼
                               Healer Service
                                      │
                         ┌────────────┼────────────┐
                         ▼            ▼            ▼
                    Replay DLQ   Restart App   Adjust Config
```

---

## 6. Data Architecture

### 6.1 Knowledge Graph Schema (Cosmos DB)

The knowledge graph uses Cosmos DB's NoSQL API with the following document types:

```json
// Entity document
{
  "id": "entity-uuid",
  "type": "Entity",
  "name": "Quantum Entanglement",
  "entityType": "Concept",
  "topic": "quantum-computing",
  "description": "...",
  "aliases": ["EPR correlation", "spooky action at a distance"],
  "confidence": 0.92,
  "sourceCount": 14,
  "embedding": [0.012, -0.034, ...],  // 3072-dim vector
  "createdAt": "2025-01-15T...",
  "updatedAt": "2025-03-10T..."
}

// Relationship document
{
  "id": "rel-uuid",
  "type": "Relationship",
  "fromEntity": "entity-uuid-1",
  "toEntity": "entity-uuid-2",
  "relationshipType": "is_fundamental_to",
  "topic": "quantum-computing",
  "confidence": 0.88,
  "sources": ["source-uuid-1", "source-uuid-2"]
}

// Claim document
{
  "id": "claim-uuid",
  "type": "Claim",
  "statement": "Quantum entanglement has been demonstrated over distances exceeding 1,200 km",
  "topic": "quantum-computing",
  "entities": ["entity-uuid-1"],
  "confidence": 0.95,
  "sources": ["source-uuid-3"],
  "verifiedAt": "2025-03-01T...",
  "contradictions": []
}

// Source document
{
  "id": "source-uuid",
  "type": "Source",
  "url": "https://...",
  "title": "...",
  "authorityScore": 0.85,
  "contentHash": "sha256:...",
  "scrapedAt": "2025-01-10T...",
  "blobPath": "raw/2025/01/10/source-uuid.json"
}
```

**Partition strategy:** Partition by `topic` to co-locate all knowledge for a topic and enable efficient graph traversal within a topic.

### 6.2 Vector Search Strategy (Azure AI Search)

- **Index:** One index per topic (created dynamically)
- **Embedding model:** `text-embedding-3-large` (3072 dimensions) via AI Foundry
- **Indexed content:** Entity descriptions, claim statements, source summaries
- **Search patterns:**
  - Semantic similarity for deduplication
  - Hybrid search (vector + keyword) for RAG retrieval
  - Faceted search by entity type, confidence range, source authority

### 6.3 Storage Strategy

| Data | Store | Rationale |
|---|---|---|
| Knowledge graph (entities, relationships, claims) | Cosmos DB | Flexible schema, vector search, global distribution |
| Raw scraped content | Azure Blob Storage | Cost-effective bulk storage, lifecycle management |
| Vector embeddings (search index) | Azure AI Search | Optimized vector indexing, hybrid search |
| Pipeline state & configuration | Cosmos DB | Transactional consistency, low latency |
| Metrics & logs | Application Insights + Log Analytics | Integrated monitoring, KQL queries |

---

## 7. azd Deployment Model

The entire system deploys with a single `azd up` command.

### Deployment Flow

```
azd up
  │
  ├── azd provision (Bicep)
  │     ├── Resource Group
  │     ├── Container Apps Environment + Log Analytics
  │     ├── AI Foundry Account + Project + Model Deployments
  │     ├── Cosmos DB Account + Database + Containers
  │     ├── AI Search Service + Indexes
  │     ├── Service Bus Namespace + Queues + Topics
  │     ├── Storage Account + Containers
  │     ├── Key Vault
  │     ├── Container Registry
  │     └── Managed Identities + Role Assignments
  │
  └── azd deploy (Container Images)
        ├── Build & push all 8 service images to ACR
        └── Deploy Container Apps with image references
```

### Bicep Module Structure

```
infra/
├── main.bicep                    # Entry point — orchestrates all modules
├── main.parameters.json          # Default parameters
├── abbreviations.json            # Naming convention abbreviations
├── modules/
│   ├── container-apps-env.bicep  # Container Apps Environment + Log Analytics
│   ├── container-app.bicep       # Reusable Container App module
│   ├── ai-foundry.bicep          # AI Foundry Account + Project + Models
│   ├── cosmos-db.bicep           # Cosmos DB account + database + containers
│   ├── ai-search.bicep           # Azure AI Search service
│   ├── service-bus.bicep         # Service Bus namespace + queues + topics
│   ├── storage.bicep             # Storage account + blob containers
│   ├── key-vault.bicep           # Key Vault
│   ├── container-registry.bicep  # Azure Container Registry
│   ├── monitoring.bicep          # Application Insights + Monitor
│   └── identity.bicep            # Managed identities + RBAC role assignments
```

### azure.yaml Configuration

```yaml
name: selflearning
services:
  scraper:
    project: ./src/scraper
    language: python
    host: containerapp
  extractor:
    project: ./src/extractor
    language: python
    host: containerapp
  knowledge:
    project: ./src/knowledge
    language: python
    host: containerapp
  reasoner:
    project: ./src/reasoner
    language: python
    host: containerapp
  evaluator:
    project: ./src/evaluator
    language: python
    host: containerapp
  orchestrator:
    project: ./src/orchestrator
    language: python
    host: containerapp
  healer:
    project: ./src/healer
    language: python
    host: containerapp
  api:
    project: ./src/api
    language: python
    host: containerapp
```

### Environment Variables (per Container App)

All services receive these via Container Apps secrets (sourced from Key Vault):

| Variable | Source | Description |
|---|---|---|
| `AZURE_AI_FOUNDRY_ENDPOINT` | AI Foundry Project | Endpoint for model inference |
| `AZURE_COSMOS_ENDPOINT` | Cosmos DB | Database connection |
| `AZURE_SERVICEBUS_NAMESPACE` | Service Bus | Messaging connection |
| `AZURE_STORAGE_ACCOUNT` | Storage Account | Blob storage endpoint |
| `AZURE_SEARCH_ENDPOINT` | AI Search | Vector search endpoint |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | App Insights | Telemetry |

Authentication uses **managed identity** everywhere — no connection strings or API keys in environment variables.

---

## 8. Project Structure

```
selflearning/
├── azure.yaml                     # azd project definition
├── README.md                      # Project overview and quickstart
├── .env.example                   # Template for local development env vars
├── .gitignore                     # Git ignore rules
│
├── docs/
│   └── architecture.md            # This document
│
├── infra/                         # Azure infrastructure (Bicep)
│   ├── main.bicep                 # Entry point
│   ├── main.parameters.json       # Parameters
│   └── modules/                   # Bicep modules (one per Azure service)
│       ├── container-apps-env.bicep
│       ├── container-app.bicep
│       ├── ai-foundry.bicep
│       ├── cosmos-db.bicep
│       ├── ai-search.bicep
│       ├── service-bus.bicep
│       ├── storage.bicep
│       ├── key-vault.bicep
│       ├── container-registry.bicep
│       ├── monitoring.bicep
│       └── identity.bicep
│
├── src/                           # Application source code
│   ├── scraper/                   # Web scraping service
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── README.md
│   ├── extractor/                 # Knowledge extraction service
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── README.md
│   ├── knowledge/                 # Knowledge graph service
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── README.md
│   ├── reasoner/                  # Reasoning & synthesis service
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── README.md
│   ├── evaluator/                 # Self-evaluation service
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── README.md
│   ├── orchestrator/              # Pipeline orchestration service
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── README.md
│   ├── healer/                    # Self-healing service
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── README.md
│   └── api/                       # API gateway service
│       ├── Dockerfile
│       ├── pyproject.toml
│       └── README.md
│
└── tests/                         # Integration and end-to-end tests
    └── README.md
```

---

## 9. Communication Patterns

### Service Bus Topology

| Queue / Topic | Publisher | Subscriber | Message Type |
|---|---|---|---|
| `scrape-requests` (queue) | Orchestrator | Scraper | Scrape target (query, URL, config) |
| `scrape-complete` (topic) | Scraper | Extractor | Raw content reference (blob path, metadata) |
| `extraction-complete` (topic) | Extractor | Knowledge Service | Structured knowledge units |
| `reasoning-requests` (queue) | Orchestrator | Reasoner | Reasoning task (topic, focus area) |
| `reasoning-complete` (topic) | Reasoner | Knowledge Service, Orchestrator | Insights, gap reports |
| `evaluation-complete` (topic) | Evaluator | Orchestrator | Expertise scorecards |
| `healing-events` (topic) | All Services | Healer | Error events, health signals |

### Synchronous Communication

- Knowledge Service exposes an internal HTTP API (Container Apps internal ingress) for graph queries
- API Gateway exposes external HTTP API (Container Apps external ingress); external authentication via Microsoft Entra ID is *planned but not yet implemented*
- Internal service-to-service HTTP calls are unauthenticated within the Container Apps environment; managed identity is used for all Azure SDK connections (Cosmos DB, Service Bus, Blob Storage, AI Foundry). Full managed-identity HTTP auth between services is *planned*.

---

## 10. Security Architecture

| Concern | Approach |
|---|---|
| **Authentication** | Microsoft Entra ID for external users *(planned)*; managed identity for Azure SDK connections (Cosmos DB, Service Bus, Blob Storage, AI Foundry) *(implemented)* |
| **Authorization** | RBAC on all Azure resources; least-privilege per service |
| **Secrets** | Key Vault for any external secrets; managed identity eliminates most secrets |
| **Network** | Container Apps Environment provides internal network isolation; external ingress only on API Gateway |
| **Data** | Encryption at rest (Azure-managed keys); encryption in transit (TLS) |
| **AI Safety** | Content filtering on AI Foundry model deployments; output validation in Extractor |

---

## 11. Cost Optimization

| Strategy | Implementation |
|---|---|
| **Scale to zero** | All Container Apps scale to 0 replicas when idle |
| **Serverless AI** | Pay-per-token model deployments (no reserved capacity) |
| **Serverless DB** | Cosmos DB serverless tier (pay per RU consumed) |
| **Consumption messaging** | Service Bus Standard tier (no premium reservation) |
| **Lifecycle management** | Blob Storage lifecycle policies to tier old raw content to Cool/Archive |
| **Smart batching** | Extractor batches multiple documents per LLM call where possible |

---

## Appendix: Technology Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Knowledge storage | Cosmos DB NoSQL (not graph API) | Better vector search support, serverless tier, wider SDK support |
| Vector search | Azure AI Search (not Cosmos DB native vectors alone) | More mature vector indexing, hybrid search, faceted filtering |
| Messaging | Service Bus (not Event Grid) | Queue semantics with dead-letter support, ordered delivery, sessions |
| Container orchestration | Container Apps (not AKS) | Simpler operations, built-in KEDA, scale-to-zero, lower ops burden |
| AI models | Serverless API deployments (not managed compute) | Pay-per-token, no GPU reservation, faster scaling |
| IaC | Bicep (not Terraform) | Native Azure, first-class azd support, simpler for Azure-only |
