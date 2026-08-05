"""Integration catalogue tests -- Milestone 11 Task Group E.

Every shipped spec is validated here, which is what makes a catalogue
of data safe: a malformed entry cannot reach an install, and the
properties that matter across all of them (https endpoints, scopes
inside the shared vocabulary, mutating operations correctly marked) are
asserted once over the whole catalogue rather than eleven times by
hand.

These are also the Phase 1 connector tests the brief asks for: each
Google integration's identity, scopes and key operations are pinned, so
a later edit that changes an endpoint or widens a scope has to say so
in a diff.
"""

from __future__ import annotations

import pytest

from jarvis.core.integrations.catalogue import (
    AVAILABLE_SPECS,
    available_ids,
    build_all,
    build_spec,
    describe_catalogue,
    vendors,
)
from jarvis.core.integrations.google import (
    GOOGLE_AUTHORIZE_URL,
    GOOGLE_REVOKE_URL,
    GOOGLE_TOKEN_URL,
)
from jarvis.core.integrations.models import (
    MUTATING_METHODS,
    IntegrationError,
)
from jarvis.core.mcp.auth.credentials import AuthMethod
from jarvis.core.plugins.sdk import PERMISSION_SCOPES

_ALL = build_all()


# --- whole-catalogue properties -------------------------------------------------


def test_every_shipped_spec_validates() -> None:
    """The test that makes a data catalogue safe."""
    for spec in _ALL:
        spec.validate()


def test_the_catalogue_is_not_empty() -> None:
    assert len(_ALL) == 11
    assert len(available_ids()) == len(AVAILABLE_SPECS)


def test_every_endpoint_is_https() -> None:
    for spec in _ALL:
        assert spec.base_url.startswith("https://"), spec.integration_id
        for operation in spec.operations:
            if operation.base_url:
                assert operation.base_url.startswith("https://")


def test_every_jarvis_permission_is_in_the_shared_vocabulary() -> None:
    """There is no second permission vocabulary in this milestone."""
    for spec in _ALL:
        assert set(spec.required_permissions) <= PERMISSION_SCOPES, spec.integration_id


def test_every_operation_requests_network_egress() -> None:
    """An outbound call the operator cannot refuse would be a gate with
    no lever."""
    for spec in _ALL:
        for operation in spec.operations:
            assert "network" in operation.permissions, f"{spec.integration_id}.{operation.name}"


def test_mutating_operations_are_marked_by_their_method() -> None:
    """The gateway refuses to retry these and never caches them, so the
    marking is load-bearing rather than descriptive."""
    for spec in _ALL:
        for operation in spec.operations:
            assert operation.mutating == (operation.method in MUTATING_METHODS)


def test_every_integration_id_is_unique_and_matches_its_key() -> None:
    for integration_id in available_ids():
        assert build_spec(integration_id).integration_id == integration_id


def test_every_operation_name_is_unique_within_its_integration() -> None:
    for spec in _ALL:
        assert len(set(spec.operation_names)) == len(spec.operation_names)


def test_a_search_operation_when_named_exists_and_accepts_a_query() -> None:
    """Otherwise the search source registered for it would send a query
    the vendor ignores and report no results forever."""
    for spec in _ALL:
        if not spec.search_operation:
            continue
        operation = spec.operation(spec.search_operation)
        accepted = {*operation.query, *operation.body}
        assert accepted & {"q", "query", "filters"}, spec.integration_id


def test_an_unknown_integration_names_the_alternatives() -> None:
    with pytest.raises(IntegrationError, match="Available:"):
        build_spec("microsoft_outlook")


def test_describe_summarises_without_the_full_operation_list() -> None:
    summaries = describe_catalogue()

    assert len(summaries) == len(_ALL)
    first = summaries[0]
    assert "operation_count" in first
    assert "operations" not in first


def test_the_shipped_vendors_are_phase_one() -> None:
    """Phases 2-6 are catalogue entries deliberately not written from
    memory -- see `catalogue.py`."""
    assert vendors() == ("google",)


# --- Google auth ----------------------------------------------------------------


def test_every_google_spec_uses_googles_oauth_endpoints() -> None:
    for spec in _ALL:
        assert spec.auth.method is AuthMethod.OAUTH2
        assert spec.auth.authorize_url == GOOGLE_AUTHORIZE_URL
        assert spec.auth.token_url == GOOGLE_TOKEN_URL
        assert spec.auth.revoke_url == GOOGLE_REVOKE_URL


def test_google_asks_for_offline_access_so_a_refresh_token_is_issued() -> None:
    """Without access_type=offline Google issues no refresh token at
    all, and the integration would stop working an hour later with
    nothing to explain it."""
    for spec in _ALL:
        assert spec.auth.authorize_params["access_type"] == "offline"


def test_no_spec_carries_a_client_secret() -> None:
    """A spec is source code; a client secret is deployment
    configuration."""
    for spec in _ALL:
        rendered = str(spec.as_dict())
        assert "client_secret" not in rendered
        assert "client_id" not in rendered


def test_scopes_are_the_narrow_ones_where_a_narrow_one_exists() -> None:
    """Listing every file a user owns is not a capability an assistant
    should hold by default, and a scope is the only place that decision
    is enforceable."""
    drive = build_spec("google_drive")
    gmail = build_spec("google_gmail")

    assert "https://www.googleapis.com/auth/drive.file" in drive.required_scopes
    assert "https://www.googleapis.com/auth/drive" not in drive.required_scopes
    assert "https://mail.google.com/" not in gmail.required_scopes


# --- Phase 1 connectors ---------------------------------------------------------


def test_gmail_covers_the_brief() -> None:
    gmail = build_spec("google_gmail")
    names = set(gmail.operation_names)

    assert {
        "messages.list",
        "messages.search",
        "messages.get",
        "messages.send",
        "messages.modify",
        "messages.attachment",
        "threads.get",
        "threads.list",
        "drafts.create",
        "drafts.list",
        "labels.list",
        "labels.get",
    } <= names


def test_gmail_send_needs_the_send_scope_not_the_read_one() -> None:
    send = build_spec("google_gmail").operation("messages.send")

    assert send.scopes == ("https://www.googleapis.com/auth/gmail.send",)
    assert send.mutating is True


def test_gmail_unread_counts_come_from_the_labels_endpoint() -> None:
    """Gmail has no unread-count endpoint; a label carries
    messagesUnread, which is why labels.get is the operation."""
    assert build_spec("google_gmail").has_operation("labels.get")


def test_calendar_covers_events_and_availability() -> None:
    calendar = build_spec("google_calendar")

    assert {
        "calendars.list",
        "events.list",
        "events.get",
        "events.insert",
        "events.patch",
        "events.delete",
        "freebusy.query",
    } <= set(calendar.operation_names)


def test_meet_links_are_created_through_calendar() -> None:
    """Meet has no scheduling API of its own; the link is conferenceData
    on a Calendar event."""
    insert = build_spec("google_calendar").operation("events.insert")

    assert "conferenceData" in insert.body
    assert "conferenceDataVersion" in insert.query


def test_the_meet_integration_says_what_it_actually_does() -> None:
    meet = build_spec("google_meet")

    assert "conferenceRecords" in meet.operation("conferences.list").path
    assert "conferenceData" in meet.availability_note


def test_drive_covers_browse_upload_move_and_sharing() -> None:
    drive = build_spec("google_drive")

    assert {
        "files.list",
        "files.get",
        "files.download",
        "files.create",
        "files.upload",
        "files.update",
        "files.delete",
        "files.copy",
        "permissions.list",
        "permissions.create",
        "permissions.delete",
    } <= set(drive.operation_names)


def test_drive_move_is_expressed_as_parent_changes() -> None:
    """Drive has no 'move'; it is addParents/removeParents on update."""
    update = build_spec("google_drive").operation("files.update")

    assert "addParents" in update.query
    assert "removeParents" in update.query


def test_drive_upload_uses_the_upload_host_path() -> None:
    upload = build_spec("google_drive").operation("files.upload")

    assert upload.path.startswith("/upload/")
    assert "resumable" in upload.description


def test_drive_file_operations_need_filesystem_permission() -> None:
    """Reading vendor bytes onto this machine is a filesystem concern as
    well as a network one."""
    drive = build_spec("google_drive")

    assert "filesystem" in drive.operation("files.download").permissions
    assert "filesystem" in drive.operation("files.upload").permissions


def test_docs_sheets_and_slides_edit_through_batch_update() -> None:
    """All three Google editors express edits as a batchUpdate request
    list, which is why each spec has one rather than a dozen
    field-specific operations."""
    for integration_id, operation in (
        ("google_docs", "documents.batch_update"),
        ("google_sheets", "spreadsheets.batch_update"),
        ("google_slides", "presentations.batch_update"),
    ):
        spec = build_spec(integration_id)
        assert spec.operation(operation).path.endswith(":batchUpdate")
        assert "requests" in spec.operation(operation).body


def test_sheets_formula_entry_is_a_value_input_option() -> None:
    """USER_ENTERED makes '=SUM(A1:A9)' a formula; RAW makes it text.
    Formula generation is that parameter, not a separate endpoint."""
    update = build_spec("google_sheets").operation("values.update")

    assert "valueInputOption" in update.query
    assert "valueInputOption" in update.required


def test_sheets_csv_import_lands_on_append() -> None:
    append = build_spec("google_sheets").operation("values.append")
    assert append.path.endswith(":append")
    assert "CSV import" in append.description


def test_contacts_uses_the_people_api_with_required_field_masks() -> None:
    """The People API refuses a request that names no fields to return,
    which is why the masks are marked required rather than optional."""
    contacts = build_spec("google_contacts")

    assert "personFields" in contacts.operation("people.list").required
    assert "readMask" in contacts.operation("people.search").required


def test_tasks_and_keep_state_that_sync_is_not_implemented() -> None:
    """Two-way sync needs a conflict policy and a scheduler; M7 Phase 6
    has not shipped. Saying so beats a mirror that loses an edit."""
    for integration_id in ("google_tasks", "google_keep"):
        note = build_spec(integration_id).availability_note
        assert "sync" in note.lower()
        assert "scheduler" in note.lower() or "M7" in note


def test_keep_declares_its_enterprise_only_availability() -> None:
    """So the REST surface can say so before a caller spends an OAuth
    round trip discovering it."""
    note = build_spec("google_keep").availability_note

    assert "Workspace" in note
    assert "consumer" in note


def test_keep_notes_touch_the_memory_permission() -> None:
    keep = build_spec("google_keep")

    assert "memory.read" in keep.operation("notes.list").permissions
    assert "memory.write" in keep.operation("notes.create").permissions


def test_photos_search_is_a_filter_post_not_a_text_query() -> None:
    """Google Photos has no free-text search; filters are its query
    language, and pretending otherwise would ship a search box that
    silently ignores what is typed into it."""
    search = build_spec("google_photos").operation("media.search")

    assert search.method == "POST"
    assert "filters" in search.body
    assert "no free-text search" in search.description
