#!/usr/bin/env sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$PROJECT_DIR"

WAIT_SECONDS=${STOCKPILOT_START_TIMEOUT:-300}
WITH_REDIS=0
BUILD=1

usage() {
    cat <<'EOF'
Usage: ./start.sh [options]

Start StockPilot locally with Docker Compose.

Options:
  --with-redis  Start the optional Redis service.
  --no-build    Reuse the existing API image without rebuilding it.
  -h, --help    Show this help message.

Environment:
  STOCKPILOT_START_TIMEOUT  Health-check timeout in seconds (default: 300).
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --with-redis)
            WITH_REDIS=1
            ;;
        --no-build)
            BUILD=0
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Error: unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
    shift
done

if ! command -v docker >/dev/null 2>&1; then
    echo "Error: Docker is not installed or is not in PATH." >&2
    echo "Install and start Docker Desktop, then run ./start.sh again." >&2
    exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
    echo "Error: Docker Compose is unavailable." >&2
    echo "Update Docker Desktop, then run ./start.sh again." >&2
    exit 1
fi

if ! docker info >/dev/null 2>&1; then
    echo "Error: Docker Desktop is not running." >&2
    echo "Start Docker Desktop, wait until it is ready, then run ./start.sh again." >&2
    exit 1
fi

if [ ! -f .env ]; then
    if [ ! -f .env.example ]; then
        echo "Error: .env.example is missing." >&2
        exit 1
    fi
    cp .env.example .env
    echo "Created .env from .env.example."
fi

if ! docker compose config --quiet; then
    echo "Error: Docker Compose configuration is invalid." >&2
    exit 1
fi

echo "Starting StockPilot..."
start_services() {
    if [ "$WITH_REDIS" -eq 1 ]; then
        if [ "$BUILD" -eq 1 ]; then
            docker compose --profile redis up --build -d postgres redis api
        else
            docker compose --profile redis up -d postgres redis api
        fi
    else
        if [ "$BUILD" -eq 1 ]; then
            docker compose up --build -d postgres api
        else
            docker compose up -d postgres api
        fi
    fi
}

attempt=1
while ! start_services; do
    if [ "$attempt" -ge 3 ]; then
        echo "Error: Docker Compose failed after ${attempt} attempts." >&2
        echo "Check the network connection and Docker Desktop, then run ./start.sh again." >&2
        exit 1
    fi
    delay=$((attempt * 5))
    echo "Docker Compose failed (attempt ${attempt}/3); retrying in ${delay}s..." >&2
    sleep "$delay"
    attempt=$((attempt + 1))
done

API_CONTAINER=$(docker compose ps -q api)
if [ -z "$API_CONTAINER" ]; then
    echo "Error: the API container was not created." >&2
    docker compose ps >&2
    exit 1
fi

echo "Waiting for the API health check (up to ${WAIT_SECONDS}s)..."
elapsed=0
while [ "$elapsed" -lt "$WAIT_SECONDS" ]; do
    health=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$API_CONTAINER" 2>/dev/null || true)
    case "$health" in
        healthy)
            echo "StockPilot is ready."
            echo "API documentation: http://localhost:8000/docs"
            echo "Health endpoint:  http://localhost:8000/health"
            echo "Stop command:     docker compose down"
            exit 0
            ;;
        unhealthy|exited|dead)
            echo "Error: API container state is $health." >&2
            break
            ;;
    esac
    sleep 2
    elapsed=$((elapsed + 2))
done

echo "Error: StockPilot did not become healthy within ${WAIT_SECONDS}s." >&2
echo "Recent container logs:" >&2
docker compose logs --tail=120 postgres api >&2 || true
exit 1
