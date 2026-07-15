#!/usr/bin/env sh
set -eu

cd /opt/stockpilot/repo
result=0

/usr/bin/docker compose --env-file .env.vps -f docker-compose.vps.yml run \
    --rm --no-deps api stockpilot sync-sector-data \
    --sector-type industry --no-members || result=1

/usr/bin/docker compose --env-file .env.vps -f docker-compose.vps.yml run \
    --rm --no-deps api stockpilot sync-sector-data \
    --sector-type concept --no-members || result=1

exit "$result"
