"""Vercel serverless entrypoint — re-exports the FastAPI app from main."""

import main

app = main.app
