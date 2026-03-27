import json
import os
import sys
from asyncio import create_subprocess_exec
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from settings import Settings


@dataclass
class BrandDocument:
    title: str
    body: str
    source_url: str | None = None
    image_urls: list[str] | None = None


class AirbyteClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._access_token: str | None = None

    async def read_brand_context(self, connection_id: str | None = None) -> list[BrandDocument]:
        resolved_connection_id = connection_id or self.settings.airbyte_connection_id
        if not resolved_connection_id:
            return []

        documents = self._load_documents_from_snapshot()
        if documents:
            return documents

        connection = await self.get_connection_details(resolved_connection_id)
        destination = None
        destination_id = connection.get("destinationId")
        if isinstance(destination_id, str) and destination_id:
            destination = await self.get_destination_details(destination_id)

        summary = json.dumps(
            {
                "connection": {
                    "connectionId": connection.get("connectionId"),
                    "name": connection.get("name"),
                    "status": connection.get("status"),
                },
                "destination": {
                    "destinationId": destination.get("destinationId") if destination else None,
                    "name": destination.get("name") if destination else None,
                    "destinationType": destination.get("destinationType") if destination else None,
                },
            },
            ensure_ascii=True,
        )
        return [
            BrandDocument(
                title="Airbyte connection metadata",
                body=(
                    "Airbyte connection metadata was available, but no synced brand document snapshot path was configured. "
                    "Set AIRBYTE_SYNCED_BRAND_JSON_PATH to a JSON export from the destination so the agent can read real brand content. "
                    f"Metadata: {summary}"
                ),
            )
        ]

    async def read_notion_brand_context(self) -> list[BrandDocument]:
        if not self.settings.airbyte_notion_connector_id:
            return []

        payload = await self._load_notion_documents_via_mcp()
        if not payload:
            return []

        title = payload.get("title")
        body = payload.get("body")
        if not isinstance(title, str) or not title.strip() or not isinstance(body, str) or not body.strip():
            return []

        image_urls = payload.get("image_urls")
        return [
            BrandDocument(
                title=title.strip(),
                body=body.strip(),
                source_url=payload.get("url") if isinstance(payload.get("url"), str) else None,
                image_urls=image_urls if isinstance(image_urls, list) else [],
            )
        ]

    async def get_connection_details(self, connection_id: str) -> dict[str, Any]:
        return await self._get(f"/connections/{connection_id}")

    async def get_destination_details(self, destination_id: str) -> dict[str, Any]:
        return await self._get(f"/destinations/{destination_id}")

    async def _get(self, path: str) -> dict[str, Any]:
        token = await self._get_access_token()
        if not token:
            return {}

        headers = {"Authorization": f"Bearer {token}"}
        url = f"{self.settings.airbyte_api_url.rstrip('/')}{path}"
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()

    async def _get_access_token(self) -> str | None:
        if self.settings.airbyte_api_key:
            return self.settings.airbyte_api_key

        if self._access_token:
            return self._access_token

        client_id = self.settings.airbyte_client_id.strip()
        client_secret = (self.settings.airbyte_client_secret or self.settings.airbyte_secret).strip()
        if not (client_id and client_secret):
            return None

        url = f"{self.settings.airbyte_api_url.rstrip('/')}/applications/token"
        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

        token = data.get("access_token")
        if not isinstance(token, str) or not token.strip():
            return None

        self._access_token = token.strip()
        return self._access_token

    async def _load_notion_documents_via_mcp(self) -> dict[str, Any] | None:
        project_root = Path(__file__).resolve().parents[1]
        helper_path = project_root / "agent" / "airbyte_notion_fetch.py"
        runtime_python = project_root / ".airbyte-venv" / "bin" / "python"
        config_dir = project_root / ".airbyte-agent-config"
        config_file = config_dir / "notion.yaml"

        if not runtime_python.exists() or not helper_path.exists() or not config_file.exists():
            return None

        env = os.environ.copy()
        airbyte_venv = project_root / ".airbyte-venv"
        airbyte_bin = airbyte_venv / "bin"
        env.update(
            {
                "AIRBYTE_CLIENT_ID": self.settings.airbyte_client_id,
                "AIRBYTE_CLIENT_SECRET": self.settings.airbyte_client_secret or self.settings.airbyte_secret,
                "AIRBYTE_AGENT_CONFIG_DIR": str(config_dir),
                "AIRBYTE_NOTION_CONFIG_FILE": str(config_file),
                "AIRBYTE_NOTION_PAGE_ID": self.settings.airbyte_notion_page_id,
                "VIRTUAL_ENV": str(airbyte_venv),
                "PATH": f"{airbyte_bin}:{env.get('PATH', '')}",
            }
        )

        process = await create_subprocess_exec(
            str(runtime_python),
            str(helper_path),
            cwd=str(project_root),
            env=env,
            stdout=-1,
            stderr=-1,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_output = stderr.decode("utf-8", errors="ignore").strip() or stdout.decode("utf-8", errors="ignore").strip()
            raise RuntimeError(f"Airbyte Notion MCP fetch failed: {error_output}")

        output = stdout.decode("utf-8", errors="ignore").strip()
        if not output:
            return None

        return json.loads(output)

    def _load_documents_from_snapshot(self) -> list[BrandDocument]:
        if not self.settings.airbyte_synced_brand_json_path:
            return []

        snapshot_path = Path(self.settings.airbyte_synced_brand_json_path).expanduser()
        if not snapshot_path.exists():
            raise FileNotFoundError(f"Airbyte snapshot file not found: {snapshot_path}")

        data = json.loads(snapshot_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            rows = data.get("documents") or data.get("items") or data.get("posts") or []
        elif isinstance(data, list):
            rows = data
        else:
            rows = []

        documents: list[BrandDocument] = []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            title = self._pick_first_string(row, ["title", "name", "slug"]) or f"Document {index + 1}"
            body = self._pick_first_string(
                row,
                ["body", "content", "html", "plaintext", "text", "excerpt"],
            )
            if not body:
                continue
            documents.append(
                BrandDocument(
                    title=title,
                    body=body,
                    source_url=self._pick_first_string(row, ["url", "canonical_url", "source_url"]),
                )
            )
        return documents

    @staticmethod
    def _pick_first_string(row: dict[str, Any], keys: list[str]) -> str | None:
        for key in keys:
            value = row.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None
