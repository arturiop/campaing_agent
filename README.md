# Campaign Agent

Standalone hackathon service for turning synced brand context into a creative brief and storyboard draft.

## Phase 1 Scope

- FastAPI app with `/generate-brief` and `/publish`
- environment-driven settings
- request/response schemas
- stubs for Airbyte, Auth0, Ghost, and orchestration

## Current Implementation

- Auth0 client credentials token request is implemented
- Ghost Admin API publish is implemented via integration key JWT auth
- OpenAI brief generation is implemented with deterministic fallback
- Airbyte connection metadata requests are implemented
- synced brand document reads come from `AIRBYTE_SYNCED_BRAND_JSON_PATH`

Airbyte itself does not expose your synced record contents directly through the Cloud control-plane API. The agent can inspect the connection and destination via Airbyte, but to read real brand documents it still needs access to the destination snapshot or export.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

## Endpoints

- `GET /health`
- `POST /generate-brief`
- `POST /publish`
