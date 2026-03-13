# Remote ACR Builds

> **Local Docker is NOT required** to build or deploy container images for this project.
> Images are built remotely in Azure Container Registry (ACR) using `az acr build`.

---

## Quick Start for New Developers

If you just joined the project and want to build and deploy without installing Docker:

```bash
# 1. Install the Azure CLI (if you haven't already)
# https://learn.microsoft.com/cli/azure/install-azure-cli

# 2. Log in to Azure
az login

# 3. Provision the environment (first time only)
azd init
azd up

# 4. Build all service images remotely
./scripts/acr-build.sh

# 5. Done — your images are live in ACR and ready for deployment
```

---

## Prerequisites

| Requirement | Notes |
|---|---|
| [`az` CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) | Azure CLI, authenticated via `az login` |
| [`azd` CLI](https://aka.ms/azd) | Azure Developer CLI for environment management |
| Azure subscription | With an ACR instance provisioned by `azd up` |
| **Docker** | ❌ **Not required** for remote builds |

> **Note:** `docker-compose.yml` is still available if you _want_ to run the full stack locally
> with Docker. See [Local Development with Docker Compose](#local-development-with-docker-compose) below.

---

## Building Images Remotely

The `scripts/acr-build.sh` script delegates all image builds to Azure Container Registry.
Your machine only needs the `az` CLI — no Docker daemon required.

### Build all services

```bash
./scripts/acr-build.sh
```

This queues a remote build in ACR for every service (`api`, `scraper`, `extractor`,
`knowledge`, `reasoner`, `evaluator`, `orchestrator`, `healer`, `ui`).
To see all available services dynamically, run `ls src/*/Dockerfile`.

### Build a single service

```bash
./scripts/acr-build.sh api
```

Replace `api` with any service name. Useful when you only changed one service and want
a fast turnaround.

### Checking build status in ACR

```bash
# Your registry name is set by azd up — retrieve it with:
echo $AZURE_CONTAINER_REGISTRY_NAME

# List the most recent builds for your registry
az acr task list-runs --registry $AZURE_CONTAINER_REGISTRY_NAME --output table

# Stream logs for a specific build run
az acr task logs --registry $AZURE_CONTAINER_REGISTRY_NAME --run-id <RUN_ID>
```

You can also view builds in the [Azure Portal](https://portal.azure.com) under
**Container Registry → Runs**.

---

## Image Tagging Strategy

Every build produces two tags for each service image:

| Tag | Description |
|---|---|
| `latest` | Always points to the most recent successful build |
| `<git-sha>` | Immutable tag tied to the exact commit (first 7 characters of the SHA) |

Example tags for the `api` service:
```
myregistry.azurecr.io/api:latest
myregistry.azurecr.io/api:a1b2c3d
```

Using the SHA tag lets you pin deployments to a specific commit and roll back safely.

---

## CI/CD Workflow

The GitHub Actions workflow at `.github/workflows/acr-build.yml` automatically builds all
service images on every push to the `main` branch:

1. **Trigger:** push to `main`
2. **Authentication:** the workflow uses an Azure service principal (stored as a GitHub
   secret) to authenticate with ACR — no manual login required.
3. **Build:** `az acr build` is called for each service in parallel.
4. **Tagging:** both `latest` and the commit SHA tag are applied.
5. **Deploy (optional):** downstream jobs can trigger a rolling update on Azure Container Apps.

No Docker is installed on the CI runner. All image builds happen server-side in ACR.

---

## Local Development with Docker Compose

If you have Docker installed and prefer to run the full stack locally, the
`docker-compose.yml` at the repo root is still available:

```bash
cp .env.example .env
# Fill in AZURE_AI_FOUNDRY_ENDPOINT and AZURE_SERVICEBUS_NAMESPACE

docker compose up --build
```

See the main [README](../README.md#local-development-with-docker-compose) for the full
local development guide including service URLs and emulator setup.

The two workflows **complement each other**:

| Workflow | When to use |
|---|---|
| `./scripts/acr-build.sh` (remote) | Building images for deployment; no Docker required |
| `docker compose up` (local) | Full local stack with hot-reload; requires Docker |

---

## Troubleshooting

### `az: command not found`
Install the Azure CLI: <https://learn.microsoft.com/cli/azure/install-azure-cli>

### `ERROR: Please run 'az login' to setup account`
Run `az login` and follow the browser prompt.

### `The registry '<name>' could not be found`
Make sure you have run `azd up` at least once to provision the ACR instance, and that
your `AZURE_CONTAINER_REGISTRY_NAME` environment variable (set by `azd`) is correct.

### Build queued but no progress
Check the ACR run logs:
```bash
az acr task list-runs --registry $AZURE_CONTAINER_REGISTRY_NAME --output table
```
