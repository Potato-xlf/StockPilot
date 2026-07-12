#!/usr/bin/env sh
set -eu
alembic upgrade head
echo "Database migration complete."

