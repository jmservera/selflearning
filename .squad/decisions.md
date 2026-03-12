# Squad Decisions

## Active Decisions

### System Architecture (2026-03-12)

**Author:** Morpheus (Lead/Architect)  
**Status:** Accepted

Eight-service microservice architecture for selflearning AI project:

1. **Eight-service microservice architecture** — Scraper, Extractor, Knowledge, Reasoner, Evaluator, Orchestrator, Healer, and API Gateway. Each is an independent Container App with its own scaling rules. **Rationale:** Each stage of the learning pipeline has different scaling characteristics and failure modes. Independence allows targeted scaling and isolated fault recovery.

2. **Azure Service Bus for inter-service communication** — Queues for point-to-point (scrape-requests, reasoning-requests). Topics with subscriptions for pub/sub (scrape-complete, extraction-complete, reasoning-complete, evaluation-complete, healing-events). **Rationale:** Dead-letter queues are essential for self-healing. KEDA integration with Container Apps enables event-driven scaling. Ordered delivery and sessions support pipeline coordination.

3. **Cosmos DB NoSQL** for knowledge storage — Knowledge graph stored as document types (Entity, Relationship, Claim, Source) in Cosmos DB NoSQL API with serverless tier, partitioned by topic. **Rationale:** NoSQL API has better vector search support, serverless pricing tier, and wider SDK coverage than Graph API. Graph traversal is handled at the application layer.

4. **Azure AI Search for vector search** — Dedicated AI Search service for vector indexing with hybrid search (vector + keyword). **Rationale:** More mature vector indexing, hybrid search support, faceted filtering. Cosmos DB vectors are good for point lookups but AI Search is better for complex search patterns.

5. **Serverless API model deployments** in AI Foundry — GPT-4o, GPT-4o-mini, and text-embedding-3-large deployed as serverless pay-per-token endpoints. **Rationale:** No GPU reservation needed, faster scaling, cost-effective for variable workloads. The system has bursty inference patterns that don't justify reserved compute.

6. **Bicep for IaC** — All infrastructure defined in Bicep modules under `infra/`. **Rationale:** Native Azure support, first-class azd integration, simpler for Azure-only deployments. No state file management needed.

7. **Managed identity everywhere** — Single user-assigned managed identity with RBAC roles on all Azure resources. **Rationale:** Eliminates secret management for service-to-service auth. Reduces attack surface. Simplifies rotation and compliance.

8. **Three-layer self-healing architecture** — Layer 1 (Infrastructure): Azure-native auto-restart, KEDA scaling. Layer 2 (Pipeline): Healer service processes DLQs, circuit breaking, endpoint failover. Layer 3 (Cognitive): Prompt tuning, learning strategy adjustment, knowledge refresh. **Rationale:** Each layer handles different failure modes. Infrastructure healing is automatic. Pipeline healing recovers from transient failures. Cognitive healing adapts the system's learning strategy.

9. **Python-first, FastAPI for all services** — All services use Python 3.12+ with FastAPI and uvicorn. **Rationale:** Consistent stack across all AI/ML workloads. FastAPI provides async support, auto-docs, and type safety. Azure SDK has first-class Python support.

## Governance

- All meaningful changes require team consensus
- Document architectural decisions here
- Keep history focused on work, decisions focused on direction
