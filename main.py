from fastapi import FastAPI

from agent.graph import CampaignAgent
from schemas import GenerateBriefRequest, GenerateBriefResponse, PublishRequest, PublishResponse
from settings import get_settings


settings = get_settings()
app = FastAPI(title="Campaign Agent API", version="0.1.0")
campaign_agent = CampaignAgent(settings)


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/generate-brief", response_model=GenerateBriefResponse)
async def generate_brief(request: GenerateBriefRequest) -> GenerateBriefResponse:
    return await campaign_agent.generate_brief(request)


@app.post("/publish", response_model=PublishResponse)
async def publish(request: PublishRequest) -> PublishResponse:
    return await campaign_agent.publish(request)
