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
- [Docker](https://www.docker.com/) for local container builds
- [Python 3.12+](https://www.python.org/)
- An Azure subscription

### Deploy to Azure

```bash
# Login to Azure
azd auth login

# Initialize environment
azd init

# Provision infrastructure and deploy all services
azd up
```

### Local Development

```bash
# Copy environment template
cp .env.example .env
# Fill in .env with your Azure resource endpoints

# Install dependencies for a service
cd src/<service>
pip install -r requirements.txt

# Run a service locally
python -m uvicorn main:app --reload --port 8000
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
│   └── api/                # API gateway
├── tests/                  # Integration tests
└── docs/                   # Documentation
```

## License

TBD
