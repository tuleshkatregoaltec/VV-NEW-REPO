#!/usr/bin/env bash

set -euo pipefail

set -a
source .env.dev
set +a

uv run --project backend python -c "import json; import sys; sys.path.insert(0, 'backend'); import app.main; print(json.dumps(app.main.app.openapi(), indent=2))" > frontend/openapi.json
cd frontend
bunx biome format --write openapi.json
rm -rf src/lib/api/generated/hey-api/client src/lib/api/generated/hey-api/core
bun run generate-client
bun run lint
