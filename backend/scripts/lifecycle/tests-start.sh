#!/usr/bin/env sh

set -eu

uv run alembic upgrade head
uv run pytest -o cache_dir=/tmp/pytest-cache tests "$@"
