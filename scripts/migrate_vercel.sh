#!/usr/bin/env bash
# Run Alembic migrations against the Vercel production Neon database.
# Prerequisites: Neon installed on the project (`vercel integration add neon`).
set -euo pipefail

cd "$(dirname "$0")/.."

echo "Pulling production env from Vercel..."
vercel pull --yes --environment=production

ENV_FILE=".vercel/.env.production.local"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE — add Neon via: vercel integration add neon"
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

if [[ -z "${DATABASE_URL:-}" && -z "${POSTGRES_URL:-}" ]]; then
  echo "No DATABASE_URL in Vercel project. Install Neon:"
  echo "  vercel integration add neon"
  echo "Or set DATABASE_URL in Vercel → Settings → Environment Variables"
  exit 1
fi

echo "Running migrations (direct/unpooled URL when available)..."
python -m pip install -q -e .
alembic upgrade head
echo "Migrations complete."
