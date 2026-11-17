# Local setup — macOS / Apple Silicon

1. Install Docker Desktop for Mac and start it.
2. Extract the ZIP into a development folder.
3. In Terminal, enter the project folder and create `.env` from `.env.example`.
4. Change `POSTGRES_PASSWORD`, `APP_DB_PASSWORD` and `MIGRATOR_DB_PASSWORD` in `.env` (use alphanumeric values) and keep `.env` untracked.
5. Run `docker compose up --build -d`.
6. Check `docker compose ps` and `curl http://localhost:8000/health`.
7. Open API docs at `http://localhost:8000/docs`, frontend at `http://localhost:5173`, and Mailpit at `http://localhost:8025`.

## Optional Ollama

Install Ollama for macOS, run `ollama pull qwen2.5:3b`, then `ollama serve`. Keep `OLLAMA_BASE_URL=http://host.docker.internal:11434` for API-in-Docker. This model is optional and is not downloaded by Docker Compose.

## Disk-space caution

The machine used for development has limited SSD capacity. Download only one small quantized Ollama model at a time. Before deleting Docker volumes or model caches, inspect what is using disk; `docker compose down -v` deletes the local PostgreSQL data volume.

## Troubleshooting

- API not ready: `docker compose logs -f api db redis mailpit`.
- Migration issue: inspect API logs before resetting the DB.
- Mail not visible: open Mailpit and inspect `email_outbox` status through the authenticated API/database; check that the API can resolve `mailpit:1025`.
- Ollama unavailable: verify `ollama serve` on the Mac and `curl http://localhost:11434/api/tags` on the host.
