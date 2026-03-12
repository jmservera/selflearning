# API Gateway Service

External HTTP interface for users and integrations.

## Responsibilities

- Topic management: create, configure, prioritize learning topics
- Knowledge query: search and browse the knowledge graph
- Expertise dashboard: view scorecards, learning progress, system health
- Learning control: pause, resume, adjust learning strategies
- Authentication via Microsoft Entra ID

## API Endpoints (planned)

| Method | Path | Description |
|---|---|---|
| POST | `/topics` | Create a new learning topic |
| GET | `/topics` | List all topics with status |
| GET | `/topics/{id}` | Get topic details and expertise scorecard |
| POST | `/topics/{id}/learn` | Trigger learning cycle |
| GET | `/knowledge/search` | Search the knowledge graph |
| GET | `/knowledge/entities/{id}` | Get entity details |
| GET | `/health` | System health dashboard |
| GET | `/health/services` | Individual service health |

## Azure Dependencies

- Azure Cosmos DB (via Knowledge Service API)
- Azure Service Bus (publish commands to Orchestrator)
- Microsoft Entra ID (authentication)
- Application Insights (health dashboard data)

## Running Locally

```bash
pip install -r pyproject.toml
uvicorn api.main:app --reload --port 8000
```
