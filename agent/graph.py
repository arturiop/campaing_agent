from typing import TypedDict

from agent.airbyte import AirbyteClient
from agent.brief import BriefGenerator
from agent.ghost import GhostClient
from auth.auth0 import Auth0M2MClient
from langgraph.graph import END, START, StateGraph
from schemas import GenerateBriefRequest, GenerateBriefResponse, PublishRequest, PublishResponse
from settings import Settings


class GenerateState(TypedDict, total=False):
    request: GenerateBriefRequest
    auth_token: str
    documents: list
    result: GenerateBriefResponse


class PublishState(TypedDict, total=False):
    request: PublishRequest
    auth_token: str
    result: PublishResponse


class CampaignAgent:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.auth0 = Auth0M2MClient(settings)
        self.airbyte = AirbyteClient(settings)
        self.brief_generator = BriefGenerator(settings)
        self.ghost = GhostClient(settings)
        self.generate_graph = self._build_generate_graph()
        self.publish_graph = self._build_publish_graph()

    async def generate_brief(self, request: GenerateBriefRequest) -> GenerateBriefResponse:
        result = await self.generate_graph.ainvoke({"request": request})
        return result["result"]

    async def publish(self, request: PublishRequest) -> PublishResponse:
        result = await self.publish_graph.ainvoke({"request": request})
        return result["result"]

    def _build_generate_graph(self):
        graph = StateGraph(GenerateState)
        graph.add_node("authenticate", self._authenticate_generate)
        graph.add_node("ingest", self._ingest_brand_context)
        graph.add_node("generate", self._generate_storyboard_brief)
        graph.add_edge(START, "authenticate")
        graph.add_edge("authenticate", "ingest")
        graph.add_edge("ingest", "generate")
        graph.add_edge("generate", END)
        return graph.compile()

    def _build_publish_graph(self):
        graph = StateGraph(PublishState)
        graph.add_node("authenticate", self._authenticate_publish)
        graph.add_node("publish", self._publish_to_ghost)
        graph.add_edge(START, "authenticate")
        graph.add_edge("authenticate", "publish")
        graph.add_edge("publish", END)
        return graph.compile()

    async def _authenticate_generate(self, state: GenerateState) -> GenerateState:
        return {"auth_token": await self.auth0.get_access_token()}

    async def _ingest_brand_context(self, state: GenerateState) -> GenerateState:
        request = state["request"]
        if request.source == "ghost":
            ghost_documents = await self.ghost.read_brand_context()
            notion_documents = await self.airbyte.read_notion_brand_context()
            documents = [*ghost_documents, *notion_documents]
        else:
            documents = await self.airbyte.read_brand_context(request.connection_id)
        return {"documents": documents}

    async def _generate_storyboard_brief(self, state: GenerateState) -> GenerateState:
        request = state["request"]
        documents = state.get("documents", [])
        result = await self.brief_generator.generate(request.project_uuid, documents)
        return {"result": result}

    async def _authenticate_publish(self, state: PublishState) -> PublishState:
        return {"auth_token": await self.auth0.get_access_token()}

    async def _publish_to_ghost(self, state: PublishState) -> PublishState:
        request = state["request"]
        result = await self.ghost.publish_brief(
            project_uuid=request.project_uuid,
            brief=request.brief,
            scenes=request.scenes,
            ghost_site_url=str(request.ghost_site_url),
        )
        return {"result": result}
