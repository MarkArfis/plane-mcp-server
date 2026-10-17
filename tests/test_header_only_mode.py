"""The http-header mode serves only the API-key endpoint and needs no OAuth configuration.

The full http mode builds the OAuth provider too and refuses to start without
PLANE_OAUTH_PROVIDER_CLIENT_ID; a self-hosted server behind a gateway that sends the PAT
(Authorization: Bearer) and X-Workspace-slug with every request has no OAuth app to configure.
"""

import pytest
from starlette.testclient import TestClient

from plane_mcp.__main__ import ServerMode, build_header_only_app
from plane_mcp.auth import PlaneHeaderAuthProvider

INITIALIZE = {
    "jsonrpc": "2.0",
    "method": "initialize",
    "id": 1,
    "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}},
}
ACCEPT = {"Accept": "application/json, text/event-stream"}


@pytest.fixture(autouse=True)
def no_oauth_env(monkeypatch):
    for name in ("PLANE_OAUTH_PROVIDER_CLIENT_ID", "PLANE_OAUTH_PROVIDER_CLIENT_SECRET"):
        monkeypatch.delenv(name, raising=False)


def test_mode_is_selectable_by_name():
    assert ServerMode("http-header") is ServerMode.HTTP_HEADER


def test_starts_without_oauth_configuration():
    with TestClient(build_header_only_app(), raise_server_exceptions=False) as client:
        response = client.post("/http/api-key/mcp", json=INITIALIZE, headers=ACCEPT)
    assert response.status_code in (401, 403)


def test_accepts_api_key_headers(monkeypatch):
    async def valid(self, token):
        return True

    # The real check calls Plane's /users/me/; here only the routing is under test.
    monkeypatch.setattr(PlaneHeaderAuthProvider, "_validate_api_key", valid)
    headers = {**ACCEPT, "Authorization": "Bearer plane_api_test", "X-Workspace-slug": "work"}
    with TestClient(build_header_only_app(), raise_server_exceptions=False) as client:
        response = client.post("/http/api-key/mcp", json=INITIALIZE, headers=headers)
    assert response.status_code == 200
    assert '"serverInfo"' in response.text


def test_oauth_and_sse_routes_are_not_served():
    with TestClient(build_header_only_app(), raise_server_exceptions=False) as client:
        assert client.post("/http/mcp", json=INITIALIZE, headers=ACCEPT).status_code == 404
        assert client.get("/sse").status_code == 404


def test_path_prefix():
    with TestClient(build_header_only_app("/plane"), raise_server_exceptions=False) as client:
        assert client.post("/plane/http/api-key/mcp", json=INITIALIZE, headers=ACCEPT).status_code in (401, 403)
