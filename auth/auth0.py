import httpx

from settings import Settings


class Auth0M2MClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def get_access_token(self) -> str:
        if not (
            self.settings.auth0_domain
            and self.settings.auth0_audience
            and self.settings.auth0_m2m_client_id
            and self.settings.auth0_m2m_client_secret
        ):
            return ""

        domain = self.settings.auth0_domain.removeprefix("https://").rstrip("/")
        token_url = f"https://{domain}/oauth/token"
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.settings.auth0_m2m_client_id,
            "client_secret": self.settings.auth0_m2m_client_secret,
            "audience": self.settings.auth0_audience,
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(token_url, json=payload)
            response.raise_for_status()
            data = response.json()

        return data["access_token"]
