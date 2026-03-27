from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent.graph import CampaignAgent
from agent.ghost import GhostClient
from schemas import GenerateBriefRequest, GenerateBriefResponse, PublishRequest, PublishResponse
from settings import get_settings


settings = get_settings()
app = FastAPI(title="Campaign Agent API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3030",
        "http://127.0.0.1:3030",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

campaign_agent = CampaignAgent(settings)
ghost_client = GhostClient(settings)


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/debug/ghost-posts")
async def debug_ghost_posts() -> dict:
    posts = await ghost_client.read_posts()
    return {
        "count": len(posts),
        "posts": posts,
    }


@app.post("/generate-brief", response_model=GenerateBriefResponse)
async def generate_brief(request: GenerateBriefRequest) -> GenerateBriefResponse:
    return await campaign_agent.generate_brief(request)


@app.post("/publish", response_model=PublishResponse)
async def publish(request: PublishRequest) -> PublishResponse:
    return await campaign_agent.publish(request)
