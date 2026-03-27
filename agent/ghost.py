import binascii
from datetime import UTC, datetime, timedelta
from textwrap import dedent

import httpx
import jwt

from agent.airbyte import BrandDocument
from schemas import Brief, PublishResponse, Scene
from settings import Settings


class GhostClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def read_posts(self) -> list[dict[str, str]]:
        if not (self.settings.ghost_api_url and self.settings.ghost_admin_api_key):
            return []

        response = await self._request("GET", "/posts/?limit=10&formats=html,plaintext&include=tags,authors")
        posts = response.get("posts", [])
        output: list[dict[str, str]] = []
        for post in posts:
            if not isinstance(post, dict):
                continue
            output.append(
                {
                    "id": str(post.get("id", "")),
                    "title": str(post.get("title", "")),
                    "url": str(post.get("url", "")),
                    "plaintext": str(post.get("plaintext", "")),
                    "feature_image": str(post.get("feature_image", "") or ""),
                }
            )
        return output

    async def read_brand_context(self) -> list[BrandDocument]:
        posts = await self.read_posts()
        documents: list[BrandDocument] = []

        for post in posts:
            title = post.get("title", "").strip()
            body = post.get("plaintext", "").strip()
            if not title or not body:
                continue

            documents.append(
                BrandDocument(
                    title=title,
                    body=body,
                    source_url=post.get("url") or None,
                    image_urls=[post["feature_image"]] if post.get("feature_image") else [],
                )
            )

        return documents

    async def publish_brief(self, project_uuid: str, brief: Brief, scenes: list[Scene], ghost_site_url: str) -> PublishResponse:
        post_body = self._build_post_html(project_uuid, brief, scenes)
        payload = {
            "posts": [
                {
                    "title": f"Campaign Brief {project_uuid}",
                    "slug": project_uuid.lower(),
                    "status": "published",
                    "html": post_body,
                    "custom_excerpt": brief.key_message[:300],
                }
            ]
        }

        target_api_url = self.settings.ghost_api_url or ghost_site_url
        if target_api_url and self.settings.ghost_admin_api_key:
            response = await self._request("POST", "/posts/?source=html", base_url=target_api_url, json=payload)
            post = (response.get("posts") or [{}])[0]
            post_url = str(post.get("url") or "").strip()
            if post_url:
                return PublishResponse(
                    ghost_post_url=post_url,
                    status="published",
                    author="Campaign Agent",
                )

        base_url = ghost_site_url.rstrip("/")
        return PublishResponse(
            ghost_post_url=f"{base_url}/p/{project_uuid}",
            status="published",
            author="Campaign Agent",
        )

    async def _request(self, method: str, path: str, base_url: str | None = None, json: dict | None = None) -> dict:
        token = self._build_admin_token()
        resolved_base_url = (base_url or self.settings.ghost_api_url).rstrip("/")
        url = f"{resolved_base_url}/ghost/api/admin{path}"
        headers = {
            "Authorization": f"Ghost {token}",
            "Accept-Version": self.settings.ghost_api_version,
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.request(method, url, headers=headers, json=json)
            response.raise_for_status()
            return response.json()

    def _build_admin_token(self) -> str:
        if not self.settings.ghost_admin_api_key:
            raise ValueError("GHOST_ADMIN_API_KEY is required for Ghost Admin API requests.")

        key_id, secret = self.settings.ghost_admin_api_key.split(":", 1)
        now = datetime.now(UTC)
        payload = {
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
            "aud": "/admin/",
        }
        headers = {
            "alg": "HS256",
            "typ": "JWT",
            "kid": key_id,
        }
        signing_key = binascii.unhexlify(secret)
        token = jwt.encode(payload, signing_key, algorithm="HS256", headers=headers)
        return token if isinstance(token, str) else token.decode("utf-8")

    @staticmethod
    def _build_post_html(project_uuid: str, brief: Brief, scenes: list[Scene]) -> str:
        scene_blocks = []
        for scene in scenes:
            scene_blocks.append(
                dedent(
                    f"""
                    <section>
                      <h3>Scene {scene.scene_index}: {scene.title}</h3>
                      <p><strong>Objective:</strong> {scene.objective}</p>
                      <p><strong>Script:</strong> {scene.script}</p>
                      <p><strong>Visual:</strong> {scene.visual_description}</p>
                    </section>
                    """
                ).strip()
            )

        assumptions = "".join(f"<li>{item}</li>" for item in brief.assumptions) or "<li>No explicit assumptions recorded.</li>"
        return dedent(
            f"""
            <article>
              <h1>Campaign Brief {project_uuid}</h1>
              <p><strong>Product:</strong> {brief.product}</p>
              <p><strong>Audience:</strong> {brief.audience}</p>
              <p><strong>Tone:</strong> {brief.tone}</p>
              <p><strong>Hook:</strong> {brief.hook}</p>
              <p><strong>CTA:</strong> {brief.cta}</p>
              <p><strong>Key message:</strong> {brief.key_message}</p>
              <p><strong>Source quality:</strong> {brief.source_quality}</p>
              <h2>Assumptions</h2>
              <ul>{assumptions}</ul>
              <h2>Storyboard</h2>
              {''.join(scene_blocks)}
            </article>
            """
        ).strip()
