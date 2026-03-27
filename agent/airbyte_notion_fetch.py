from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import anyio
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def _extract_plain_text(items: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        plain_text = item.get("plain_text")
        if isinstance(plain_text, str) and plain_text:
            parts.append(plain_text)
    return "".join(parts).strip()


def _extract_page_title(page: dict[str, Any]) -> str:
    properties = page.get("properties")
    if not isinstance(properties, dict):
        return "Notion Campaign Context"

    title_data = properties.get("title")
    if not isinstance(title_data, dict):
        return "Notion Campaign Context"

    title_items = title_data.get("title")
    if not isinstance(title_items, list):
        return "Notion Campaign Context"

    title = _extract_plain_text(title_items)
    return title or "Notion Campaign Context"


def _extract_block_text(block: dict[str, Any]) -> str:
    block_type = block.get("type")
    if not isinstance(block_type, str):
        return ""

    block_value = block.get(block_type)
    if not isinstance(block_value, dict):
        return ""

    rich_text = block_value.get("rich_text")
    if not isinstance(rich_text, list):
        return ""

    text = _extract_plain_text(rich_text)
    if not text:
        return ""

    if block_type == "bulleted_list_item":
        return f"- {text}"
    if block_type == "numbered_list_item":
        return f"1. {text}"
    return text


def _extract_image_url(block: dict[str, Any]) -> str | None:
    if block.get("type") != "image":
        return None

    image = block.get("image")
    if not isinstance(image, dict):
        return None

    external = image.get("external")
    if isinstance(external, dict) and isinstance(external.get("url"), str):
        return external["url"]

    file_data = image.get("file")
    if isinstance(file_data, dict) and isinstance(file_data.get("url"), str):
        return file_data["url"]

    return None


def _result_data(result: Any) -> Any:
    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        return structured

    content = getattr(result, "content", None) or []
    for item in content:
        text = getattr(item, "text", None)
        if isinstance(text, str) and text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
    return None


async def _call_execute(session: ClientSession, entity: str, action: str, params: dict[str, Any]) -> Any:
    result = await session.call_tool(
        "notion__execute",
        {
            "entity": entity,
            "action": action,
            "params": params,
        },
    )
    return _result_data(result)


async def main() -> None:
    config_dir = Path(os.environ.get("AIRBYTE_AGENT_CONFIG_DIR", ".airbyte-agent-config"))
    config_path = Path(os.environ.get("AIRBYTE_NOTION_CONFIG_FILE", config_dir / "notion.yaml"))
    page_id_hint = os.environ.get("AIRBYTE_NOTION_PAGE_ID", "").strip()
    project_root = Path(__file__).resolve().parents[1]
    venv_root = Path(os.environ.get("VIRTUAL_ENV", project_root / ".airbyte-venv"))
    venv_bin = venv_root / "bin"
    env = {
        "AIRBYTE_CLIENT_ID": os.environ["AIRBYTE_CLIENT_ID"],
        "AIRBYTE_CLIENT_SECRET": os.environ["AIRBYTE_CLIENT_SECRET"],
        "PATH": f"{venv_bin}:{os.environ.get('PATH', '')}",
        "VIRTUAL_ENV": str(venv_root),
    }

    server = StdioServerParameters(
        command=str(venv_bin / "agent-engine"),
        args=["--config-dir", str(config_dir), "mcp", "serve", str(config_path)],
        env=env,
        cwd=str(config_dir.parent),
    )

    async with stdio_client(server, errlog=open(os.devnull, "w")) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            pages_response = await _call_execute(session, "pages", "list", {"page_size": 20})
            pages = pages_response.get("data", []) if isinstance(pages_response, dict) else []
            if not isinstance(pages, list) or not pages:
                raise RuntimeError("No Notion pages were returned by the Airbyte connector.")

            selected_page = None
            for page in pages:
                if isinstance(page, dict) and page.get("id") == page_id_hint:
                    selected_page = page
                    break
            if selected_page is None:
                selected_page = next((page for page in pages if isinstance(page, dict)), None)
            if selected_page is None:
                raise RuntimeError("No usable Notion page was returned by the Airbyte connector.")

            page_id = str(selected_page.get("id") or "").strip()
            if not page_id:
                raise RuntimeError("Selected Notion page did not include an id.")

            blocks_response = await _call_execute(session, "blocks", "list", {"block_id": page_id, "page_size": 100})
            blocks = blocks_response.get("data", []) if isinstance(blocks_response, dict) else []
            if not isinstance(blocks, list):
                blocks = []

            lines: list[str] = []
            image_urls: list[str] = []
            for block in blocks:
                if not isinstance(block, dict):
                    continue

                text = _extract_block_text(block)
                if " [truncated" in text:
                    block_id = block.get("id")
                    if isinstance(block_id, str) and block_id:
                        full_block = await _call_execute(session, "blocks", "get", {"block_id": block_id})
                        if isinstance(full_block, dict):
                            text = _extract_block_text(full_block) or text
                            image_url = _extract_image_url(full_block)
                            if image_url:
                                image_urls.append(image_url)

                if text:
                    lines.append(text)

                image_url = _extract_image_url(block)
                if image_url:
                    image_urls.append(image_url)

            payload = {
                "page_id": page_id,
                "title": _extract_page_title(selected_page),
                "url": selected_page.get("url"),
                "body": "\n".join(lines).strip(),
                "image_urls": list(dict.fromkeys(image_urls)),
            }
            print(json.dumps(payload, ensure_ascii=True))


if __name__ == "__main__":
    anyio.run(main)
