"""MCP server exposing Fly.io operational tools.

The FastMCP server is mounted under `/mcp` (via `streamable-http`) so it can be
registered directly in the ChatGPT MCP connector form. Tools use the Fly API
token from `FLY_API_TOKEN` by default, but callers can override it per-request
by passing `token` explicitly.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx
import structlog
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from src.api.config import settings

logger = structlog.get_logger(__name__)


class FlyAPIError(Exception):
    """Raised when the Fly API returns an error response."""


class FlyAPIClient:
    """Lightweight Fly.io HTTP client for Machines + GraphQL APIs."""

    GRAPHQL_URL = "https://api.fly.io/graphql"
    MACHINES_BASE_URL = "https://api.machines.dev/v1"

    def __init__(self, token: str) -> None:
        if not token:
            raise ValueError("Fly API token is required")

        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _graphql(self, query: str, variables: Dict[str, Any]) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.post(
                self.GRAPHQL_URL,
                json={"query": query, "variables": variables},
                headers=self._headers,
            )
            response.raise_for_status()
            payload = response.json()

        if payload.get("errors"):
            error_message = payload["errors"][0].get("message", "Unknown Fly API error")
            raise FlyAPIError(error_message)

        return payload.get("data", {})

    async def get_app_overview(self, app_name: str) -> Dict[str, Any]:
        query = """
        query($appName: String!) {
          app(name: $appName) {
            name
            status
            deployed
            organization { slug }
            platformVersion
            hostname
            currentRelease {
              id
              version
              description
              user { email }
              createdAt
              reason
            }
            regions { code name }
          }
        }
        """
        data = await self._graphql(query, {"appName": app_name})
        app = (data or {}).get("app") or {}

        if not app:
            raise FlyAPIError(f"App '{app_name}' was not found or is not accessible")

        current_release = app.get("currentRelease") or {}
        return {
            "name": app.get("name"),
            "status": app.get("status"),
            "deployed": app.get("deployed"),
            "platformVersion": app.get("platformVersion"),
            "hostname": app.get("hostname"),
            "organization": app.get("organization", {}).get("slug"),
            "regions": app.get("regions") or [],
            "currentRelease": {
                "id": current_release.get("id"),
                "version": current_release.get("version"),
                "description": current_release.get("description"),
                "reason": current_release.get("reason"),
                "createdAt": current_release.get("createdAt"),
                "initiatedBy": (current_release.get("user") or {}).get("email"),
            },
        }

    async def list_machines(self, app_name: str) -> List[Dict[str, Any]]:
        url = f"{self.MACHINES_BASE_URL}/apps/{app_name}/machines"

        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            response = await client.get(url, headers=self._headers)
            response.raise_for_status()
            machines = response.json()

        if not isinstance(machines, list):
            raise FlyAPIError("Unexpected response while listing machines")

        return [
            {
                "id": machine.get("id"),
                "name": machine.get("name"),
                "state": machine.get("state"),
                "region": machine.get("region"),
                "image": ((machine.get("config") or {}).get("image") or {}).get("ref")
                or machine.get("image"),
                "createdAt": machine.get("created_at") or machine.get("createdAt"),
            }
            for machine in machines
        ]

    async def get_recent_logs(
        self,
        app_name: str,
        limit: int = 50,
        region: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        limit = max(1, min(limit, 200))
        query = """
        query($appName: String!, $limit: Int!, $region: String) {
          app(name: $appName) {
            logs(first: $limit, region: $region) {
              edges {
                node {
                  timestamp
                  level
                  message
                  instanceId
                  region
                }
              }
            }
          }
        }
        """
        data = await self._graphql(
            query,
            {"appName": app_name, "limit": limit, "region": region},
        )
        app = (data or {}).get("app") or {}
        logs = (app.get("logs") or {}).get("edges") or []

        parsed_logs: List[Dict[str, Any]] = []
        for edge in logs:
            entry = edge.get("node") or {}
            parsed_logs.append(
                {
                    "timestamp": entry.get("timestamp"),
                    "level": entry.get("level"),
                    "message": entry.get("message"),
                    "instanceId": entry.get("instanceId"),
                    "region": entry.get("region"),
                }
            )

        return parsed_logs


def _resolve_app_name(app_name: Optional[str]) -> str:
    resolved = app_name or settings.FLY_APP_NAME
    if not resolved:
        raise ToolError("app_name is required (or set FLY_APP_NAME in the environment)")
    return resolved


def _resolve_token(token: Optional[str]) -> str:
    resolved = token or settings.FLY_API_TOKEN
    if not resolved:
        raise ToolError("FLY_API_TOKEN is not configured and no token override was provided")
    return resolved


mcp_server = FastMCP(
    name="VoiceMesh Fly Tools",
    instructions=(
        "Operational tools for VoiceMesh deployments on Fly.io. "
        "Configure FLY_API_TOKEN (and optionally FLY_APP_NAME) so ChatGPT can inspect apps, "
        "machines, and recent logs. Tools return structured JSON that is easy to chain in reasoning "
        "workflows."
    ),
    streamable_http_path="/",
    debug=settings.is_development,
    log_level=settings.LOG_LEVEL,
)


@mcp_server.tool(
    description=(
        "Get a high-level summary of a Fly.io app including status, platform version, regions, "
        "and latest release."
    ),
)
async def get_app_overview(app_name: Optional[str] = None, token: Optional[str] = None) -> Dict[str, Any]:
    client = FlyAPIClient(_resolve_token(token))
    target_app = _resolve_app_name(app_name)
    logger.info("mcp_get_app_overview", app=target_app)
    try:
        return await client.get_app_overview(target_app)
    except (FlyAPIError, httpx.HTTPError) as exc:
        logger.error("mcp_get_app_overview_error", app=target_app, error=str(exc))
        raise ToolError(str(exc)) from exc


@mcp_server.tool(
    description="List Fly.io Machines for an app with id, state, region, and image details.",
)
async def list_machines(app_name: Optional[str] = None, token: Optional[str] = None) -> List[Dict[str, Any]]:
    client = FlyAPIClient(_resolve_token(token))
    target_app = _resolve_app_name(app_name)
    logger.info("mcp_list_machines", app=target_app)
    try:
        return await client.list_machines(target_app)
    except (FlyAPIError, httpx.HTTPError) as exc:
        logger.error("mcp_list_machines_error", app=target_app, error=str(exc))
        raise ToolError(str(exc)) from exc


@mcp_server.tool(
    description="Fetch recent application logs from Fly.io (GraphQL) with optional region filter.",
)
async def get_recent_logs(
    app_name: Optional[str] = None,
    limit: int = 50,
    region: Optional[str] = None,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    client = FlyAPIClient(_resolve_token(token))
    target_app = _resolve_app_name(app_name)
    logger.info("mcp_get_recent_logs", app=target_app, limit=limit, region=region)
    try:
        logs = await client.get_recent_logs(target_app, limit=limit, region=region)
        return {"app": target_app, "count": len(logs), "logs": logs}
    except (FlyAPIError, httpx.HTTPError) as exc:
        logger.error("mcp_get_recent_logs_error", app=target_app, error=str(exc))
        raise ToolError(str(exc)) from exc


# Expose ASGI app (mounted at /mcp in FastAPI)
mcp_asgi_app = mcp_server.streamable_http_app()
