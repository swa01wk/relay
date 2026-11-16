#!/bin/sh
# docker compose for the production stack, e.g.:
#   infra/docker/prod.sh up -d --build
#   infra/docker/prod.sh logs -f gateway
#   infra/docker/prod.sh ps
set -eu
dir=$(cd "$(dirname "$0")" && pwd)
if [ ! -f "$dir/.env.prod" ]; then
  echo "Missing $dir/.env.prod: copy .env.prod.example and fill it in (see docs/deploying.md)." >&2
  exit 1
fi
exec docker compose --project-name relay-prod --env-file "$dir/.env.prod" -f "$dir/docker-compose.prod.yml" "$@"
