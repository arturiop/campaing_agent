import json
from textwrap import dedent

from openai import AsyncOpenAI

from agent.airbyte import BrandDocument
from schemas import Brief, GenerateBriefResponse, Scene
from settings import Settings


class BriefGenerator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    async def generate(self, project_uuid: str, documents: list[BrandDocument]) -> GenerateBriefResponse:
        if self.client:
            try:
                generated = await self._generate_with_openai(project_uuid, documents)
                if generated is not None:
                    return generated
            except Exception:
                pass

        return self._fallback_response(documents)

    async def _generate_with_openai(self, project_uuid: str, documents: list[BrandDocument]) -> GenerateBriefResponse | None:
        context_blocks = []
        reference_images: list[str] = []
        for index, document in enumerate(documents[:8], start=1):
            image_lines = ""
            if document.image_urls:
                image_lines = "\nReference images:\n" + "\n".join(document.image_urls[:3])
                reference_images.extend(document.image_urls[:3])
            context_blocks.append(
                f"[Document {index}]\nTitle: {document.title}\nURL: {document.source_url or 'n/a'}{image_lines}\nContent:\n{document.body[:6000]}"
            )

        prompt = dedent(
            f"""
            You are Campaign Agent, a marketing copilot that turns brand context into a reviewable creative brief and storyboard.

            Project UUID: {project_uuid}

            Return strict JSON with this shape:
            {{
              "brief": {{
                "product": "string",
                "audience": "string",
                "tone": "string",
                "hook": "string",
                "cta": "string",
                "key_message": "string",
                "source_quality": "rich" | "thin",
                "assumptions": ["string"]
              }},
              "scenes": [
                {{
                  "scene_index": 1,
                  "title": "string",
                  "objective": "string",
                  "script": "string",
                  "visual_description": "string"
                }}
              ]
            }}

            Rules:
            - Create 4 to 6 scenes.
            - Base the output on the provided brand context.
            - If context is thin, say so via source_quality and assumptions.
            - Keep each scene concise and storyboard-ready.
            - Do not wrap the JSON in markdown fences.

            Brand context:
            {chr(10).join(context_blocks) if context_blocks else "No source documents were available."}
            """
        ).strip()

        response = await self.client.responses.create(
            model=self.settings.openai_model,
            input=prompt,
        )
        text = response.output_text.strip()
        if not text:
            return None

        if text.startswith("```"):
            text = text.strip("`")
            lines = text.splitlines()
            text = "\n".join(lines[1:-1]).strip() if len(lines) >= 3 else text

        payload = json.loads(text)
        payload.setdefault("reference_images", [])
        existing_images = payload.get("reference_images") or []
        payload["reference_images"] = list(dict.fromkeys([*existing_images, *reference_images]))
        return GenerateBriefResponse.model_validate(payload)

    def _fallback_response(self, documents: list[BrandDocument]) -> GenerateBriefResponse:
        source_quality = "rich" if len(documents) >= 3 else "thin"
        assumptions: list[str] = []
        if not documents:
            assumptions.append("No synced brand documents were available, so fallback assumptions were used.")
        if source_quality == "thin":
            assumptions.append("Audience and hook should be validated by the marketer before publish.")

        brief = Brief(
            product="Placeholder product",
            audience="Performance marketers evaluating new creative directions",
            tone="Direct, modern, campaign-ready",
            hook="Skip the brief-writing step and start reviewing creative direction immediately.",
            cta="Approve the storyboard and publish the brief to the production team.",
            key_message="Campaign Agent turns existing brand context into a reviewable storyboard draft.",
            source_quality=source_quality,
            assumptions=assumptions,
        )

        scenes = [
            Scene(
                scene_index=1,
                title="Setup friction",
                objective="Frame the current pain clearly.",
                script="Every campaign starts with a blank page and manual setup.",
                visual_description="Marketer staring at a blank brief document with campaign tabs open.",
            ),
            Scene(
                scene_index=2,
                title="Agent ingest",
                objective="Show the agent pulling context automatically.",
                script="Campaign Agent reads synced brand context from Ghost through Airbyte.",
                visual_description="Dashboard cards showing synced brand posts flowing into an agent pipeline.",
            ),
            Scene(
                scene_index=3,
                title="Brief creation",
                objective="Reveal the generated brief.",
                script="The agent extracts audience, tone, hook, and CTA into a usable brief.",
                visual_description="Structured creative brief fields filling in automatically on screen.",
            ),
            Scene(
                scene_index=4,
                title="Storyboard review",
                objective="Transition from brief to storyboard.",
                script="A storyboard draft appears for quick review and revision.",
                visual_description="Four-scene storyboard grid in Watchable with clear scene cards.",
            ),
        ]

        reference_images: list[str] = []
        for document in documents:
            if document.image_urls:
                reference_images.extend(document.image_urls)

        return GenerateBriefResponse(
            brief=brief,
            scenes=scenes,
            reference_images=list(dict.fromkeys(reference_images)),
        )
