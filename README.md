# selflearning

A self-learning AI system that scrapes the internet for knowledge on a given topic, becomes a PhD-level expert, and continuously self-heals and self-improves.

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full system architecture.

### Services

| Service | Description |
|---|---|
| **Scraper** | Discovers and retrieves content from the internet |
| **Extractor** | Transforms raw content into structured knowledge units |
| **Knowledge** | Manages the knowledge graph (entities, relationships, claims) |
| **Reasoner** | Synthesizes knowledge, identifies gaps, generates insights |
| **Evaluator** | Measures expertise level and identifies weaknesses |
| **Orchestrator** | Drives the learning pipeline — decides what to learn next |
| **Healer** | Monitors health, detects failures, triggers recovery |
| **API** | External HTTP interface for users and integrations |

### Azure Services

- **Azure AI Foundry** — LLM inference, embeddings, AI agents
- **Azure Container Apps** — All microservices (scale-to-zero)
- **Azure Cosmos DB** — Knowledge graph storage (serverless)
- **Azure AI Search** — Vector search over knowledge
- **Azure Service Bus** — Event-driven messaging between services
- **Azure Blob Storage** — Raw scraped content
- **Azure Key Vault** — Secrets management
- **Azure Monitor** — Observability

## Getting Started

### Prerequisites

- [Azure Developer CLI (azd)](https://aka.ms/azd)
- [Azure CLI (az)](https://learn.microsoft.com/cli/azure/install-azure-cli) - authenticated via `az login`
- [Python 3.12+](https://www.python.org/)
- An Azure subscription
- [Docker](https://www.docker.com/) and [Docker Compose](https://docs.docker.com/compose/) *(optional — only needed for local development; remote builds do not require Docker)*

### Deploy to Azure

```bash
# Login to Azure
azd auth login

# Initialize environment
azd init

# Provision infrastructure and deploy all services
azd up
```

## Building & Deploying

> **Local Docker is NOT required** to build container images.
> Images are built remotely in Azure Container Registry (ACR).
> See **[docs/remote-builds.md](docs/remote-builds.md)** for the full guide.

```bash
# Build all services (remote — no Docker needed)
./scripts/acr-build.sh

# Build a single service
./scripts/acr-build.sh api
```

Images are tagged with both `latest` and the git commit SHA.
The CI/CD pipeline (GitHub Actions) runs these builds automatically on every push to `main`.

---

### Local Development with Docker Compose

The `docker-compose.yml` at the repo root starts all services locally.
[Azure Cosmos DB emulator](https://learn.microsoft.com/azure/cosmos-db/docker-emulator) and
[Azurite](https://learn.microsoft.com/azure/storage/common/storage-use-azurite) (Blob Storage)
run as containers.  Azure Service Bus and Azure AI Foundry still require live Azure resources.

```bash
# 1. Copy the environment template
cp .env.example .env

# 2. Fill in the required values in .env:
#    AZURE_AI_FOUNDRY_ENDPOINT  — your Azure AI Foundry endpoint
#    AZURE_SERVICEBUS_NAMESPACE — your Service Bus namespace (optional; pipelines
#                                 won't process messages without it, but all
#                                 services will still start and pass health checks)

# 3. Build and start everything
docker compose up --build

# 4. Open the UI
#    http://localhost:5173
```

| Service | Local URL |
|---|---|
| UI | <http://localhost:5173> |
| API | <http://localhost:8000> |
| Knowledge | <http://localhost:8004> |
| Evaluator | <http://localhost:8006> |
| Orchestrator | <http://localhost:8007> |
| Healer | <http://localhost:8008> |
| Scraper | <http://localhost:8001> |
| Extractor | <http://localhost:8002> |
| Reasoner | <http://localhost:8003> |
| Cosmos DB emulator | <https://localhost:8081> |
| Azurite (Blob) | <http://localhost:10000> |

> **Cosmos DB emulator SSL** — The emulator uses a self-signed certificate.
> Browsers and tools that perform strict TLS validation will show a warning.
> Download the emulator certificate from `https://localhost:8081/_explorer/emulator.pem`
> and trust it locally, or configure your client to skip verification for
> the emulator endpoint.
>
> **Service Bus** — No Docker emulator exists for Azure Service Bus.
> Set `AZURE_SERVICEBUS_NAMESPACE` in `.env` to enable event-driven pipelines.
> Without it, all services still start and respond to health checks but
> message-driven flows (scraping, extraction, reasoning, evaluation) are inactive.
>
> **AI endpoints** — Set `AZURE_AI_FOUNDRY_ENDPOINT` to enable LLM calls.
> Services start without it but AI-dependent operations will fail.

#### Running a single service without Docker

```bash
# Copy environment template
cp .env.example .env
# Fill in .env with your Azure resource endpoints

# Create and populate a virtual environment, then install dependencies for a service
uv venv .venv
cd src/<service>
uv pip install --python ../../.venv/bin/python -r pyproject.toml

# Run a service locally (activate the venv first, or prefix with the full path)
../../.venv/bin/python -m uvicorn main:app --reload --port 8000
```

## Project Structure

```
selflearning/
├── azure.yaml              # azd project definition
├── infra/                  # Bicep infrastructure templates
│   ├── main.bicep          # Entry point
│   └── modules/            # One module per Azure service
├── src/                    # Application source code
│   ├── scraper/            # Web scraping service
│   ├── extractor/          # Knowledge extraction
│   ├── knowledge/          # Knowledge graph management
│   ├── reasoner/           # Reasoning & synthesis
│   ├── evaluator/          # Self-evaluation
│   ├── orchestrator/       # Pipeline orchestration
│   ├── healer/             # Self-healing
│   ├── api/                # API gateway
│   └── ui/                 # React web UI
├── tests/                  # Integration tests
└── docs/                   # Documentation
```

## License

TBD
