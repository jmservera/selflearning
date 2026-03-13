#!/usr/bin/env bash
# scripts/acr-build.sh
#
# Build Docker images remotely on Azure Container Registry using `az acr build`.
# No local Docker installation required.
#
# Usage:
#   ./scripts/acr-build.sh                   # build all services
#   ./scripts/acr-build.sh api               # build a single service
#   ./scripts/acr-build.sh api ui            # build specific services
#
# Options:
#   --registry <name>    ACR name (overrides ACR_NAME env var and azd discovery)
#
# Environment variables:
#   ACR_NAME             ACR registry name (without .azurecr.io suffix)

set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ALL_SERVICES=(api scraper extractor knowledge reasoner evaluator orchestrator healer ui)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

log()  { echo "[acr-build] $*"; }
err()  { echo "[acr-build] ERROR: $*" >&2; }
die()  { err "$*"; exit 1; }

usage() {
  cat <<EOF
Usage: $(basename "$0") [--registry <acr-name>] [service ...]

Build Docker images remotely on Azure Container Registry.

Options:
  --registry <name>    ACR name (without .azurecr.io suffix)

Environment variables:
  ACR_NAME             ACR name (without .azurecr.io suffix)

Examples:
  $(basename "$0")               # build all services
  $(basename "$0") api           # build just the API
  $(basename "$0") api ui        # build API and UI
  ACR_NAME=myregistry $(basename "$0")
EOF
}

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------

REGISTRY="${ACR_NAME:-}"
REQUESTED_SERVICES=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --registry)
      [[ $# -lt 2 ]] && die "--registry requires an argument"
      REGISTRY="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    -*)
      die "Unknown option: $1"
      ;;
    *)
      REQUESTED_SERVICES+=("$1")
      shift
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Validate prerequisites
# ---------------------------------------------------------------------------

if ! command -v az &>/dev/null; then
  die "Azure CLI ('az') is not installed. Install it from https://aka.ms/install-azure-cli"
fi

if ! az account show &>/dev/null; then
  die "Not logged in to Azure CLI. Run 'az login' first."
fi

# ---------------------------------------------------------------------------
# Discover ACR name if not provided
# ---------------------------------------------------------------------------

if [[ -z "${REGISTRY}" ]]; then
  log "ACR_NAME not set — attempting to discover from azd environment..."
  if command -v azd &>/dev/null; then
    REGISTRY=$(azd env get-values 2>/dev/null \
      | grep 'AZURE_CONTAINER_REGISTRY_NAME' \
      | sed 's/AZURE_CONTAINER_REGISTRY_NAME=//;s/"//g' \
      | tr -d '[:space:]' || true)
  fi
fi

if [[ -z "${REGISTRY}" ]]; then
  die "ACR name could not be determined. Provide --registry <name>, set ACR_NAME, or run 'azd provision' first."
fi

log "Using ACR: ${REGISTRY}"

# ---------------------------------------------------------------------------
# Determine services to build
# ---------------------------------------------------------------------------

if [[ ${#REQUESTED_SERVICES[@]} -eq 0 ]]; then
  SERVICES=("${ALL_SERVICES[@]}")
else
  SERVICES=("${REQUESTED_SERVICES[@]}")
fi

# Validate requested services
for svc in "${SERVICES[@]}"; do
  dockerfile="${REPO_ROOT}/src/${svc}/Dockerfile"
  if [[ ! -f "${dockerfile}" ]]; then
    die "Unknown service '${svc}': no Dockerfile found at ${dockerfile}"
  fi
done

# ---------------------------------------------------------------------------
# Determine git short SHA for dual tagging
# ---------------------------------------------------------------------------

GIT_SHA=$(git -C "${REPO_ROOT}" rev-parse --short HEAD 2>/dev/null || echo "unknown")

# ---------------------------------------------------------------------------
# Build each service
# ---------------------------------------------------------------------------

TOTAL=${#SERVICES[@]}
CURRENT=0

for svc in "${SERVICES[@]}"; do
  CURRENT=$((CURRENT + 1))
  log "Building service '${svc}' (${CURRENT} of ${TOTAL})..."

  image_latest="selflearning-${svc}:latest"
  image_sha="selflearning-${svc}:${GIT_SHA}"
  context="${REPO_ROOT}/src/${svc}/"

  az acr build \
    --registry "${REGISTRY}" \
    --image "${image_latest}" \
    --image "${image_sha}" \
    --file "Dockerfile" \
    "${context}"

  log "Successfully built '${svc}' → ${REGISTRY}.azurecr.io/${image_latest}"
done

log "All ${TOTAL} service(s) built successfully."
