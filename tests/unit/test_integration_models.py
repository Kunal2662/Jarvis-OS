"""Integration spec tests -- Milestone 11 Task Group E.

The pure half: validation, path rendering and parameter splitting. No
database, no network, no container -- which is the point of connectors
being data. The path-rendering tests are security tests: a caller
supplies parameters and never a path, and these pin that a parameter
cannot become one.
"""

from __future__ import annotations

import pytest

from jarvis.core.integrations.models import (
    HTTP_METHODS,
    MUTATING_METHODS,
    OPERATION_CATEGORIES,
    AuthSpec,
    IntegrationError,
    IntegrationSpec,
    OperationSpec,
)
from jarvis.core.mcp.auth.credentials import AuthMethod
from jarvis.core.plugins.sdk import PERMISSION_SCOPES


def _operation(**overrides) -> OperationSpec:
    defaults = {
        "name": "messages.list",
        "method": "GET",
        "path": "/v1/users/{user_id}/messages",
        "description": "List messages.",
        "permissions": ("network",),
        "scopes": ("vendor.read",),
        "query": ("q", "maxResults"),
    }
    defaults.update(overrides)
    return OperationSpec(**defaults)  # type: ignore[arg-type]


def _spec(**overrides) -> IntegrationSpec:
    defaults = {
        "integration_id": "acme_mail",
        "name": "Acme Mail",
        "vendor": "acme",
        "base_url": "https://api.acme.test",
        "auth": AuthSpec(
            method=AuthMethod.OAUTH2,
            authorize_url="https://auth.acme.test/authorize",
            token_url="https://auth.acme.test/token",
        ),
        "operations": (_operation(),),
    }
    defaults.update(overrides)
    return IntegrationSpec(**defaults)  # type: ignore[arg-type]


# --- vocabularies ---------------------------------------------------------------


def test_mutating_methods_are_a_subset_of_http_methods() -> None:
    assert MUTATING_METHODS <= HTTP_METHODS
    assert "GET" not in MUTATING_METHODS


def test_operation_categories_are_the_shipped_six() -> None:
    assert sorted(OPERATION_CATEGORIES) == [
        "admin",
        "download",
        "read",
        "search",
        "upload",
        "write",
    ]


# --- operation validation -------------------------------------------------------


def test_a_valid_operation_validates() -> None:
    _operation().validate("acme_mail")


def test_an_unknown_http_method_is_refused() -> None:
    with pytest.raises(IntegrationError, match="unknown HTTP method"):
        _operation(method="FETCH").validate("acme_mail")


def test_a_relative_path_is_refused() -> None:
    with pytest.raises(IntegrationError, match="must start with"):
        _operation(path="v1/messages").validate("acme_mail")


def test_a_bad_operation_name_is_refused() -> None:
    with pytest.raises(IntegrationError, match="dotted lowercase"):
        _operation(name="Messages List").validate("acme_mail")


def test_an_unknown_jarvis_permission_is_refused() -> None:
    """Scopes come from the fixed vocabulary the plugin platform owns --
    there is no second permission vocabulary in this milestone."""
    with pytest.raises(IntegrationError, match="unknown JARVIS permission"):
        _operation(permissions=("mail.read_everything",)).validate("acme_mail")


def test_an_operation_with_no_permissions_is_refused() -> None:
    """An operation nothing gates is an operation nothing can refuse."""
    with pytest.raises(IntegrationError, match="declares no JARVIS permissions"):
        _operation(permissions=()).validate("acme_mail")


def test_an_unknown_category_is_refused() -> None:
    with pytest.raises(IntegrationError, match="unknown category"):
        _operation(category="mystery").validate("acme_mail")


def test_required_names_must_be_declared_somewhere() -> None:
    with pytest.raises(IntegrationError, match="required, but declares them nowhere"):
        _operation(required=("nonexistent",)).validate("acme_mail")


def test_path_params_are_derived_not_declared_twice() -> None:
    operation = _operation(path="/v1/{a}/things/{b}")
    assert operation.path_params == ("a", "b")


def test_mutating_is_derived_from_the_method() -> None:
    assert _operation(method="POST").mutating is True
    assert _operation(method="GET").mutating is False


# --- path rendering: the security boundary --------------------------------------


def test_path_placeholders_are_substituted() -> None:
    rendered = _operation().render_path({"user_id": "me"})
    assert rendered == "/v1/users/me/messages"


def test_a_traversal_attempt_becomes_one_literal_segment() -> None:
    """A parameter cannot change which endpoint is called.

    The invariant is about *separators*, not about dots: ``..`` is a
    harmless name, and what would make it traversal is an unencoded
    ``/`` next to it. Every slash the caller supplied is encoded, so the
    whole value stays one path segment naming a (probably absent)
    resource, and the endpoint reached is still the one the spec
    declared.
    """
    rendered = _operation().render_path({"user_id": "../../admin"})

    assert rendered == "/v1/users/..%2F..%2Fadmin/messages"
    # Exactly the separators the template itself declares -- none added.
    assert rendered.count("/") == _operation().path.count("/")


def test_a_query_string_cannot_be_smuggled_through_a_path_parameter() -> None:
    rendered = _operation().render_path({"user_id": "me?admin=true"})

    assert "?" not in rendered
    assert "%3F" in rendered


def test_a_slash_in_a_parameter_stays_one_segment() -> None:
    rendered = _operation().render_path({"user_id": "a/b"})
    assert rendered == "/v1/users/a%2Fb/messages"


def test_a_missing_path_parameter_is_refused() -> None:
    with pytest.raises(IntegrationError, match="requires path parameter"):
        _operation().render_path({})


def test_an_empty_path_parameter_is_refused() -> None:
    """Empty would render '/v1/users//messages', which is a different
    endpoint and usually a 404 the caller cannot explain."""
    with pytest.raises(IntegrationError, match="requires path parameter"):
        _operation().render_path({"user_id": "   "})


# --- parameter splitting --------------------------------------------------------


def test_params_split_into_query_and_body() -> None:
    operation = _operation(method="POST", query=("sendUpdates",), body=("subject", "to"))
    query, body = operation.split_params(
        {"user_id": "me", "sendUpdates": "all", "subject": "hi", "to": "a@b.test"}
    )

    assert query == {"sendUpdates": "all"}
    assert body == {"subject": "hi", "to": "a@b.test"}


def test_an_undeclared_parameter_is_refused_not_forwarded() -> None:
    """A vendor would usually ignore it, but 'usually' is not a security
    property: forwarding one is a caller reaching behaviour the spec
    does not describe and the review never saw."""
    with pytest.raises(IntegrationError, match="does not accept parameter"):
        _operation().split_params({"user_id": "me", "impersonate": "someone-else"})


def test_a_missing_required_parameter_is_refused() -> None:
    operation = _operation(required=("q",))
    with pytest.raises(IntegrationError, match="requires parameter"):
        operation.split_params({"user_id": "me"})


def test_none_values_are_dropped_rather_than_sent() -> None:
    query, _ = _operation().split_params({"user_id": "me", "q": "hello", "maxResults": None})
    assert query == {"q": "hello"}


# --- capability bridge ----------------------------------------------------------


def test_an_operation_becomes_an_mcp_capability() -> None:
    """This is what makes "every connector is an MCP provider" true
    rather than decorative."""
    capability = _operation().to_capability("acme_mail")

    assert capability.name == "acme_mail.messages.list"
    assert capability.kind == "tool"
    assert capability.permissions == ("network",)
    assert capability.metadata["integration_id"] == "acme_mail"
    assert capability.metadata["vendor_scopes"] == ["vendor.read"]


def test_capability_permissions_stay_inside_the_shared_vocabulary() -> None:
    capability = _operation().to_capability("acme_mail")
    assert set(capability.permissions) <= PERMISSION_SCOPES


# --- integration validation -----------------------------------------------------


def test_a_valid_spec_validates() -> None:
    _spec().validate()


def test_a_plain_http_endpoint_is_refused() -> None:
    """The one place egress could be downgraded to cleartext."""
    with pytest.raises(IntegrationError, match="must be https"):
        _spec(base_url="http://api.acme.test").validate()


def test_loopback_http_is_allowed_for_local_test_servers() -> None:
    """Otherwise the engine could only be tested against the real
    internet -- which is how an untested engine happens."""
    _spec(base_url="http://127.0.0.1:8080").validate()
    _spec(base_url="http://localhost:8080").validate()


def test_an_oauth2_spec_without_a_token_url_is_refused() -> None:
    with pytest.raises(IntegrationError, match="declares no token_url"):
        _spec(
            auth=AuthSpec(
                method=AuthMethod.OAUTH2, authorize_url="https://auth.acme.test/authorize"
            )
        ).validate()


def test_a_spec_with_no_operations_is_refused() -> None:
    with pytest.raises(IntegrationError, match="declares no operations"):
        _spec(operations=()).validate()


def test_a_duplicate_operation_name_is_refused() -> None:
    with pytest.raises(IntegrationError, match="twice"):
        _spec(operations=(_operation(), _operation())).validate()


def test_a_search_operation_must_exist() -> None:
    with pytest.raises(IntegrationError, match="which it does not declare"):
        _spec(search_operation="nope.search").validate()


def test_looking_up_an_unknown_operation_names_the_alternatives() -> None:
    with pytest.raises(IntegrationError, match="Available:"):
        _spec().operation("nope")


# --- derived properties ---------------------------------------------------------


def test_required_scopes_unions_operations_and_auth_defaults() -> None:
    spec = _spec(
        auth=AuthSpec(
            method=AuthMethod.OAUTH2,
            authorize_url="https://auth.acme.test/authorize",
            token_url="https://auth.acme.test/token",
            default_scopes=("vendor.profile",),
        ),
        operations=(_operation(), _operation(name="messages.send", scopes=("vendor.send",))),
    )

    assert spec.required_scopes == ("vendor.profile", "vendor.read", "vendor.send")


def test_required_permissions_are_deduplicated() -> None:
    spec = _spec(
        operations=(
            _operation(),
            _operation(name="files.get", permissions=("network", "filesystem")),
        )
    )
    assert spec.required_permissions == ("filesystem", "network")


def test_a_spec_becomes_provider_metadata_the_registry_accepts() -> None:
    """The bridge into M10.5: metadata that the existing provider
    registry validates without any change to it."""
    metadata = _spec().to_metadata()
    metadata.validate()

    assert metadata.transport == "http"
    assert metadata.name == "Acme Mail"
    assert "integration" in metadata.tags
    assert metadata.capabilities == ("acme_mail.messages.list",)
