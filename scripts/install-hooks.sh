#!/usr/bin/env bash
# Install dev dependencies and register git pre-commit hooks (ruff + mypy).
set -euo pipefail
cd "$(dirname "$0")/.."

python -m pip install -e ".[dev]"
pre-commit install
echo "Git hooks installed. Commits will run ruff and mypy."
