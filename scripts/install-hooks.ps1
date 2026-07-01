# Install dev dependencies and register git pre-commit hooks (ruff + mypy).
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

python -m pip install -e ".[dev]"
pre-commit install
Write-Host "Git hooks installed. Commits will run ruff and mypy."
