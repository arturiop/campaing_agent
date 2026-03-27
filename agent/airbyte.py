import json
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


class AirbyteClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

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

    async def get_connection_details(self, connection_id: str) -> dict[str, Any]:
        return await self._get(f"/connections/{connection_id}")

    async def get_destination_details(self, destination_id: str) -> dict[str, Any]:
        return await self._get(f"/destinations/{destination_id}")

    async def _get(self, path: str) -> dict[str, Any]:
        if not self.settings.airbyte_api_key:
            return {}

        headers = {"Authorization": f"Bearer {self.settings.airbyte_api_key}"}
        url = f"{self.settings.airbyte_api_url.rstrip('/')}{path}"
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()

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
