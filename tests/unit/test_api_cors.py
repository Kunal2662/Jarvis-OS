"""CORS allowlist contract for the REST API.

Regression cover for a real P0: the packaged desktop shell could not reach
Core at all. ``ApiSettings.cors_origins`` listed only host-only origins
(``http://localhost``/``http://127.0.0.1``), but Starlette matches the *full*
origin -- scheme, host **and** port (``CORSMiddleware.is_allowed_origin`` is a
plain ``origin in self.allow_origins``). The packaged app's origin is
``http://tauri.localhost`` (verified at runtime against a real build, which
reported ``location.origin = http://tauri.localhost`` and sent that exact
``Origin`` header), so every request was rejected with
``400 Disallowed CORS origin`` and the UI showed "backend is not reachable".

These tests pin both directions: the origins that must work, and the ones
that must stay blocked. ``create_app(settings)`` is used without a container
on purpose -- CORS is app-wide middleware, so the always-mounted health route
exercises it without needing a database.

**Not covered here, deliberately:** the runtime WebSocket
(``/api/v1/ws``). Starlette's CORS middleware does not apply to WebSocket
connections at all, and ``routes/runtime_ws.py`` performs no origin check --
it authenticates purely on the ``token`` query parameter. Asserting CORS
behaviour for it would be asserting something that does not exist.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from jarvis.core.config.settings import ApiSettings, Settings
from jarvis.infrastructure.api.fastapi_server import create_app

HEALTH_PATH = "/api/v1/health"

#: Origins the product genuinely uses. Kept as literals rather than read back
#: from ``settings`` so a silent edit to the allowlist fails this test instead
#: of trivially agreeing with itself.
ALLOWED_ORIGINS = [
    "http://localhost",  # plain browser dev on port 80
    "http://127.0.0.1",  # same, loopback literal
    "http://localhost:3000",  # canonical frontend dev server / Tauri devUrl
    "http://127.0.0.1:3000",  # same, loopback literal
    "http://tauri.localhost",  # PACKAGED desktop app (Windows) -- the P0
    "tauri://localhost",  # packaged desktop app (macOS/Linux)
]

#: Origins that must never be accepted. Includes near-misses for the real
#: entries, because exact matching is the entire security property here.
BLOCKED_ORIGINS = [
    "https://evil.example",
    "http://evil.example",
    "http://tauri.localhost.evil.example",  # suffix attack on the Tauri host
    "http://evil.example/?http://tauri.localhost",  # substring smuggling
    "http://localhost:9999",  # a localhost port that is NOT configured
    "https://tauri.localhost",  # https variant (useHttpsScheme is not enabled)
    "https://localhost:3000",  # right host/port, wrong scheme
]


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(Settings()))


def _preflight(client: TestClient, origin: str):
    return client.options(
        HEALTH_PATH,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )


@pytest.mark.parametrize("origin", ALLOWED_ORIGINS)
def test_allowed_origin_passes_preflight(client: TestClient, origin: str) -> None:
    """Every origin the product actually runs under must clear preflight and
    be echoed back exactly -- never as ``*``."""
    response = _preflight(client, origin)

    assert response.status_code == 200, response.text
    assert response.headers["access-control-allow-origin"] == origin


@pytest.mark.parametrize("origin", ALLOWED_ORIGINS)
def test_allowed_origin_passes_simple_request(client: TestClient, origin: str) -> None:
    """A non-preflighted request must also carry the header, otherwise the
    browser discards the response body even on a 200."""
    response = client.get(HEALTH_PATH, headers={"Origin": origin})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


@pytest.mark.parametrize("origin", BLOCKED_ORIGINS)
def test_unapproved_origin_is_rejected_at_preflight(client: TestClient, origin: str) -> None:
    """Starlette answers a disallowed preflight with 400 and no
    ``Access-Control-Allow-Origin``."""
    response = _preflight(client, origin)

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("origin", BLOCKED_ORIGINS)
def test_unapproved_origin_gets_no_allow_header_on_simple_request(
    client: TestClient, origin: str
) -> None:
    """The request may still reach the route (CORS is enforced in the browser,
    not the server), but without the header the browser refuses to expose the
    response -- so the header's absence is the security property to pin."""
    response = client.get(HEALTH_PATH, headers={"Origin": origin})

    assert "access-control-allow-origin" not in response.headers


def test_credentials_are_enabled_and_never_paired_with_a_wildcard(client: TestClient) -> None:
    """``allow_credentials=True`` is only safe while origins stay exact: a
    wildcard combined with credentials is both spec-invalid and a real
    cross-site data-exfiltration hole."""
    response = _preflight(client, "http://tauri.localhost")

    assert response.headers["access-control-allow-credentials"] == "true"
    assert response.headers["access-control-allow-origin"] != "*"


def test_no_configured_origin_is_a_wildcard() -> None:
    """Guards the allowlist itself, independently of any request."""
    origins = Settings().api.cors_origins

    assert "*" not in origins
    assert not any("*" in origin for origin in origins)


def test_default_allowlist_contains_every_required_origin() -> None:
    """The shipped default must work out of the box -- an operator should not
    need ``JARVIS_API_CORS_ORIGINS`` just to make the packaged app function."""
    origins = Settings().api.cors_origins

    for origin in ALLOWED_ORIGINS:
        assert origin in origins, f"{origin} missing from the default allowlist"


class TestEnvOverride:
    """The escape hatch must actually work.

    Regression cover for a second, quieter outage in the same field: because
    pydantic-settings JSON-decodes ``list[str]`` environment values *before*
    field validators run, the comma-separated form documented by ``_split_csv``
    raised ``SettingsError`` and the process would not start at all. An operator
    whose setup needs a different origin reaches for exactly this variable, so a
    crash here turns a misconfiguration into an outage.
    """

    def test_comma_separated_override_is_accepted(self, monkeypatch) -> None:
        monkeypatch.setenv(
            "JARVIS_API_CORS_ORIGINS", "http://tauri.localhost,http://localhost:4200"
        )

        assert Settings().api.cors_origins == [
            "http://tauri.localhost",
            "http://localhost:4200",
        ]

    def test_single_value_override_is_accepted(self, monkeypatch) -> None:
        monkeypatch.setenv("JARVIS_API_CORS_ORIGINS", "http://tauri.localhost")

        assert Settings().api.cors_origins == ["http://tauri.localhost"]

    def test_surrounding_whitespace_is_stripped(self, monkeypatch) -> None:
        """A stray space would otherwise produce ' http://localhost', which can
        never equal any real ``Origin`` header -- a silently dead allowlist."""
        monkeypatch.setenv(
            "JARVIS_API_CORS_ORIGINS", " http://tauri.localhost , http://localhost:3000 "
        )

        assert Settings().api.cors_origins == [
            "http://tauri.localhost",
            "http://localhost:3000",
        ]

    def test_json_array_override_still_works(self, monkeypatch) -> None:
        """The one shape that worked before ``NoDecode`` must keep working."""
        monkeypatch.setenv(
            "JARVIS_API_CORS_ORIGINS", '["http://tauri.localhost", "tauri://localhost"]'
        )

        assert Settings().api.cors_origins == [
            "http://tauri.localhost",
            "tauri://localhost",
        ]

    def test_malformed_json_array_fails_loudly(self, monkeypatch) -> None:
        """Never quietly reinterpret a broken allowlist as something else."""
        monkeypatch.setenv("JARVIS_API_CORS_ORIGINS", '["http://tauri.localhost"')

        with pytest.raises(ValidationError, match="cors_origins"):
            Settings()

    def test_an_overridden_allowlist_is_actually_enforced(self, monkeypatch) -> None:
        """End of the chain: the override must reach the live middleware, not
        just the settings object."""
        monkeypatch.setenv("JARVIS_API_CORS_ORIGINS", "http://localhost:4200")
        client = TestClient(create_app(Settings()))

        allowed = _preflight(client, "http://localhost:4200")
        assert allowed.status_code == 200
        assert allowed.headers["access-control-allow-origin"] == "http://localhost:4200"

        # A default entry must now be denied -- proving the override replaced
        # the allowlist rather than being merged into it.
        denied = _preflight(client, "http://tauri.localhost")
        assert denied.status_code == 400
        assert "access-control-allow-origin" not in denied.headers


class TestWildcardRefusal:
    """A wildcard must be a boot failure, never a working configuration.

    ``create_app`` passes ``allow_credentials=True``. Starlette reacts to a
    single ``*`` entry by setting ``allow_all_origins``, and then -- precisely
    *because* credentials are on -- echoes the caller's own origin back next to
    ``Access-Control-Allow-Credentials: true`` (``CORSMiddleware.send`` ->
    ``allow_explicit_origin``). So ``*`` does not merely relax the allowlist, it
    removes it: any site on the internet could issue credentialed requests and
    read the responses. Refusing to start is the only safe failure mode; a
    silently disabled allowlist looks healthy right up until it is exploited.
    """

    @pytest.mark.parametrize(
        "value",
        [
            "*",  # bare, reachable via the comma-separated form
            '["*"]',  # JSON array -- the shape that already worked before
            "http://tauri.localhost,*",  # smuggled in beside real origins
            "https://*.example.com",  # pattern style: Starlette has no such
            # support here (that is allow_origin_regex),
            # so it is a dead entry at best
        ],
    )
    def test_a_wildcard_origin_is_refused(self, monkeypatch, value: str) -> None:
        monkeypatch.setenv("JARVIS_API_CORS_ORIGINS", value)

        with pytest.raises(ValidationError, match="wildcard CORS origin"):
            Settings()

    def test_a_wildcard_passed_directly_is_also_refused(self) -> None:
        """The guard runs ``mode="after"``, so it covers a programmatic
        construction too -- not just the environment path."""
        with pytest.raises(ValidationError, match="wildcard CORS origin"):
            ApiSettings(cors_origins=["*"])

    def test_the_real_default_still_constructs(self) -> None:
        """Guard against the guard: it must reject only wildcards."""
        assert ApiSettings().cors_origins == ALLOWED_ORIGINS
