from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


SourceType = Literal["ghost", "sheets"]
SourceQuality = Literal["rich", "thin"]


class Brief(BaseModel):
    product: str
    audience: str
    tone: str
    hook: str
    cta: str
    key_message: str
    source_quality: SourceQuality
    assumptions: list[str] = Field(default_factory=list)


class Scene(BaseModel):
    scene_index: int
    title: str
    objective: str
    script: str
    visual_description: str


class GenerateBriefRequest(BaseModel):
    source: SourceType = "ghost"
    connection_id: str | None = None
    project_uuid: str


class GenerateBriefResponse(BaseModel):
    brief: Brief
    scenes: list[Scene]
    reference_images: list[HttpUrl] = Field(default_factory=list)


class PublishRequest(BaseModel):
    project_uuid: str
    brief: Brief
    scenes: list[Scene]
    ghost_site_url: HttpUrl


class PublishResponse(BaseModel):
    ghost_post_url: HttpUrl
    status: Literal["published"]
    author: str
