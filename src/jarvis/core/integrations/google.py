"""Google Workspace catalogue -- Milestone 11 Task Group E, Phase 1.

Eleven integrations expressed as :class:`IntegrationSpec` data, executed
by the one engine in ``provider.py`` + ``gateway.py``. Every path here
is a documented Google REST endpoint; every vendor scope is a documented
Google OAuth scope. Nothing in this module makes a request or holds a
secret -- it is a catalogue, and it is reviewed the way a catalogue is:
against the vendor's published API reference.

**One OAuth client, many integrations.** Google issues one set of client
credentials per project and scopes are requested per authorization, so
:func:`google_auth` is shared and each spec contributes the scopes its
own operations need. A caller authorizing Gmail therefore consents to
Gmail scopes only -- not to the union of everything in this file.

**Scope choices are deliberately the narrow ones.** ``gmail.readonly``
rather than ``https://mail.google.com/``; ``drive.file`` (files this app
created or the user opened with it) rather than ``drive`` wherever an
operation allows it. Listing every file a user owns is not a capability
a note-taking assistant should hold by default, and a scope is the only
place that decision can actually be enforced.

**What is deliberately absent, and why.**

* *Two-way sync* for Tasks and Keep. Pull operations ship; a *sync* needs
  a conflict-resolution policy and something to run it on a cadence, and
  M7's Scheduler (Phase 6) does not exist. One-directional import that
  works beats a bidirectional sync that silently loses an edit.
* *Google Meet as its own scheduling API*. Meet links are created by
  Calendar (``conferenceData`` with ``conferenceDataVersion=1``), which
  is why the Meet operations live on the Calendar spec rather than in a
  separate integration that would have to call Calendar anyway. The Meet
  REST API v2 covers conference *records* (post-meeting artefacts), and
  that is what the ``google_meet`` spec exposes -- named for what it
  does rather than for what the phrase "Google Meet" might suggest.
* *Resumable/multipart upload.* Drive's simple upload ships (``uploadType
  =media``), which is correct up to 5 MB. Resumable upload is a
  multi-request protocol with its own session URIs, and bolting it into
  a single-request gateway would misrepresent both.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from jarvis.core.integrations.models import AuthSpec, IntegrationSpec, OperationSpec
from jarvis.core.mcp.auth.credentials import AuthMethod

if TYPE_CHECKING:
    from collections.abc import Callable

#: Google's OAuth 2.0 endpoints. One authorization server for every
#: product in this file.
GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"

_GOOGLE_APIS = "https://www.googleapis.com"

#: ``access_type=offline`` is what makes Google return a refresh token at
#: all; ``prompt=consent`` forces it to be re-issued when a user
#: re-authorizes, because Google sends a refresh token only on the first
#: consent and an integration that silently lost its would stop working
#: an hour later with no explanation.
_GOOGLE_AUTHORIZE_PARAMS = {"access_type": "offline", "prompt": "consent"}

#: Every operation needs egress. Additional JARVIS scopes are declared
#: per operation where the operation genuinely touches that subsystem.
_NET = ("network",)


def google_auth(*scopes: str) -> AuthSpec:
    """Google's OAuth configuration with a specific scope set."""
    return AuthSpec(
        method=AuthMethod.OAUTH2,
        authorize_url=GOOGLE_AUTHORIZE_URL,
        token_url=GOOGLE_TOKEN_URL,
        revoke_url=GOOGLE_REVOKE_URL,
        default_scopes=tuple(scopes),
        authorize_params=dict(_GOOGLE_AUTHORIZE_PARAMS),
    )


# ---------------------------------------------------------------------------
# Gmail
# ---------------------------------------------------------------------------
def gmail_spec() -> IntegrationSpec:
    read = "https://www.googleapis.com/auth/gmail.readonly"
    send = "https://www.googleapis.com/auth/gmail.send"
    modify = "https://www.googleapis.com/auth/gmail.modify"
    compose = "https://www.googleapis.com/auth/gmail.compose"

    return IntegrationSpec(
        integration_id="google_gmail",
        name="Gmail",
        vendor="google",
        description="Read, search, send and organize Gmail messages.",
        base_url=_GOOGLE_APIS,
        auth=google_auth(read),
        tags=("mail",),
        search_operation="messages.search",
        operations=(
            OperationSpec(
                name="messages.list",
                method="GET",
                path="/gmail/v1/users/{user_id}/messages",
                description="List message ids in the mailbox, newest first.",
                category="read",
                permissions=_NET,
                scopes=(read,),
                query=("q", "maxResults", "pageToken", "labelIds", "includeSpamTrash"),
            ),
            OperationSpec(
                name="messages.search",
                method="GET",
                path="/gmail/v1/users/{user_id}/messages",
                description=(
                    "Search the mailbox with Gmail query syntax "
                    "(from:, subject:, has:attachment, ...)."
                ),
                category="search",
                permissions=_NET,
                scopes=(read,),
                query=("q", "maxResults", "pageToken", "labelIds"),
                required=("q",),
            ),
            OperationSpec(
                name="messages.get",
                method="GET",
                path="/gmail/v1/users/{user_id}/messages/{message_id}",
                description="Fetch one message, including headers and body.",
                category="read",
                permissions=_NET,
                scopes=(read,),
                query=("format", "metadataHeaders"),
            ),
            OperationSpec(
                name="messages.send",
                method="POST",
                path="/gmail/v1/users/{user_id}/messages/send",
                description=("Send a message. 'raw' is the base64url-encoded RFC 2822 message."),
                category="write",
                permissions=_NET,
                scopes=(send,),
                body=("raw", "threadId"),
                required=("raw",),
            ),
            OperationSpec(
                name="messages.modify",
                method="POST",
                path="/gmail/v1/users/{user_id}/messages/{message_id}/modify",
                description="Add or remove labels on a message (archive, mark read, star).",
                category="write",
                permissions=_NET,
                scopes=(modify,),
                body=("addLabelIds", "removeLabelIds"),
            ),
            OperationSpec(
                name="messages.attachment",
                method="GET",
                path=(
                    "/gmail/v1/users/{user_id}/messages/{message_id}" "/attachments/{attachment_id}"
                ),
                description="Download one attachment's base64url data.",
                category="download",
                permissions=_NET,
                scopes=(read,),
            ),
            OperationSpec(
                name="threads.get",
                method="GET",
                path="/gmail/v1/users/{user_id}/threads/{thread_id}",
                description="Fetch a whole conversation thread.",
                category="read",
                permissions=_NET,
                scopes=(read,),
                query=("format", "metadataHeaders"),
            ),
            OperationSpec(
                name="threads.list",
                method="GET",
                path="/gmail/v1/users/{user_id}/threads",
                description="List conversation threads.",
                category="read",
                permissions=_NET,
                scopes=(read,),
                query=("q", "maxResults", "pageToken", "labelIds"),
            ),
            OperationSpec(
                name="drafts.create",
                method="POST",
                path="/gmail/v1/users/{user_id}/drafts",
                description="Create a draft without sending it.",
                category="write",
                permissions=_NET,
                scopes=(compose,),
                body=("message",),
                required=("message",),
            ),
            OperationSpec(
                name="drafts.list",
                method="GET",
                path="/gmail/v1/users/{user_id}/drafts",
                description="List saved drafts.",
                category="read",
                permissions=_NET,
                scopes=(read,),
                query=("maxResults", "pageToken", "q"),
            ),
            OperationSpec(
                name="labels.list",
                method="GET",
                path="/gmail/v1/users/{user_id}/labels",
                description="List labels, including the unread counts each carries.",
                category="read",
                permissions=_NET,
                scopes=(read,),
            ),
            OperationSpec(
                name="labels.get",
                method="GET",
                path="/gmail/v1/users/{user_id}/labels/{label_id}",
                description=(
                    "One label with messagesUnread/messagesTotal -- the unread count "
                    "for INBOX comes from here."
                ),
                category="read",
                permissions=_NET,
                scopes=(read,),
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Calendar (and Meet links, which Calendar creates)
# ---------------------------------------------------------------------------
def calendar_spec() -> IntegrationSpec:
    read = "https://www.googleapis.com/auth/calendar.readonly"
    write = "https://www.googleapis.com/auth/calendar.events"

    return IntegrationSpec(
        integration_id="google_calendar",
        name="Google Calendar",
        vendor="google",
        description=(
            "Read and manage calendar events, check availability, and create "
            "Meet links on events."
        ),
        base_url=_GOOGLE_APIS,
        auth=google_auth(read),
        tags=("calendar",),
        search_operation="events.list",
        operations=(
            OperationSpec(
                name="calendars.list",
                method="GET",
                path="/calendar/v3/users/me/calendarList",
                description="List the calendars this account can see.",
                category="read",
                permissions=_NET,
                scopes=(read,),
                query=("maxResults", "pageToken", "showHidden"),
            ),
            OperationSpec(
                name="events.list",
                method="GET",
                path="/calendar/v3/calendars/{calendar_id}/events",
                description=(
                    "List or search events in a window. 'q' is free-text; "
                    "singleEvents=true expands recurrence."
                ),
                category="search",
                permissions=_NET,
                scopes=(read,),
                query=(
                    "q",
                    "timeMin",
                    "timeMax",
                    "maxResults",
                    "pageToken",
                    "singleEvents",
                    "orderBy",
                    "showDeleted",
                ),
            ),
            OperationSpec(
                name="events.get",
                method="GET",
                path="/calendar/v3/calendars/{calendar_id}/events/{event_id}",
                description="Fetch one event.",
                category="read",
                permissions=_NET,
                scopes=(read,),
            ),
            OperationSpec(
                name="events.insert",
                method="POST",
                path="/calendar/v3/calendars/{calendar_id}/events",
                description=(
                    "Create an event. Pass conferenceDataVersion=1 with a "
                    "conferenceData createRequest to attach a Meet link."
                ),
                category="write",
                permissions=_NET,
                scopes=(write,),
                query=("conferenceDataVersion", "sendUpdates"),
                body=(
                    "summary",
                    "description",
                    "location",
                    "start",
                    "end",
                    "attendees",
                    "recurrence",
                    "reminders",
                    "conferenceData",
                    "visibility",
                ),
                required=("start", "end"),
            ),
            OperationSpec(
                name="events.patch",
                method="PATCH",
                path="/calendar/v3/calendars/{calendar_id}/events/{event_id}",
                description="Update part of an event.",
                category="write",
                permissions=_NET,
                scopes=(write,),
                query=("conferenceDataVersion", "sendUpdates"),
                body=(
                    "summary",
                    "description",
                    "location",
                    "start",
                    "end",
                    "attendees",
                    "recurrence",
                    "reminders",
                    "conferenceData",
                    "status",
                ),
            ),
            OperationSpec(
                name="events.delete",
                method="DELETE",
                path="/calendar/v3/calendars/{calendar_id}/events/{event_id}",
                description="Delete an event.",
                category="write",
                permissions=_NET,
                scopes=(write,),
                query=("sendUpdates",),
            ),
            OperationSpec(
                name="freebusy.query",
                method="POST",
                path="/calendar/v3/freeBusy",
                description=(
                    "Availability across calendars in a window -- the input for "
                    "conflict detection."
                ),
                category="read",
                permissions=_NET,
                scopes=(read,),
                body=("timeMin", "timeMax", "items", "timeZone"),
                required=("timeMin", "timeMax", "items"),
            ),
        ),
    )


def meet_spec() -> IntegrationSpec:
    """Google Meet **conference records** -- the post-meeting artefacts.

    Named for what the Meet REST API actually offers. Scheduling a
    meeting is a Calendar event carrying ``conferenceData``, which is why
    that operation lives on the Calendar spec: an integration whose
    "schedule a meeting" call had to turn around and call Calendar would
    be a second door to one room.
    """
    read = "https://www.googleapis.com/auth/meetings.space.readonly"

    return IntegrationSpec(
        integration_id="google_meet",
        name="Google Meet",
        vendor="google",
        description="Read Meet conference records, participants and recordings.",
        base_url="https://meet.googleapis.com",
        auth=google_auth(read),
        tags=("meetings",),
        availability_note=(
            "Meeting *creation* is a Calendar event with conferenceData -- see "
            "google_calendar.events.insert. This integration reads conference "
            "records after the fact."
        ),
        operations=(
            OperationSpec(
                name="conferences.list",
                method="GET",
                path="/v2/conferenceRecords",
                description="List past conference records.",
                category="read",
                permissions=_NET,
                scopes=(read,),
                query=("pageSize", "pageToken", "filter"),
            ),
            OperationSpec(
                name="conferences.get",
                method="GET",
                path="/v2/conferenceRecords/{conference_record}",
                description="One conference record.",
                category="read",
                permissions=_NET,
                scopes=(read,),
            ),
            OperationSpec(
                name="participants.list",
                method="GET",
                path="/v2/conferenceRecords/{conference_record}/participants",
                description="Who attended a conference.",
                category="read",
                permissions=_NET,
                scopes=(read,),
                query=("pageSize", "pageToken", "filter"),
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Drive
# ---------------------------------------------------------------------------
def drive_spec() -> IntegrationSpec:
    file_scope = "https://www.googleapis.com/auth/drive.file"
    read = "https://www.googleapis.com/auth/drive.readonly"
    metadata = "https://www.googleapis.com/auth/drive.metadata.readonly"

    return IntegrationSpec(
        integration_id="google_drive",
        name="Google Drive",
        vendor="google",
        description="Browse, upload, download and organize Drive files and folders.",
        base_url=_GOOGLE_APIS,
        auth=google_auth(file_scope),
        tags=("storage", "files"),
        search_operation="files.list",
        operations=(
            OperationSpec(
                name="files.list",
                method="GET",
                path="/drive/v3/files",
                description=(
                    "List or search files. 'q' is Drive query syntax "
                    "(name contains '...', mimeType = '...', trashed = false)."
                ),
                category="search",
                permissions=_NET,
                scopes=(read,),
                query=(
                    "q",
                    "pageSize",
                    "pageToken",
                    "orderBy",
                    "fields",
                    "spaces",
                    "includeItemsFromAllDrives",
                    "supportsAllDrives",
                ),
            ),
            OperationSpec(
                name="files.get",
                method="GET",
                path="/drive/v3/files/{file_id}",
                description="File metadata (or content when alt=media).",
                category="read",
                permissions=_NET,
                scopes=(read,),
                query=("fields", "alt", "supportsAllDrives"),
            ),
            OperationSpec(
                name="files.download",
                method="GET",
                path="/drive/v3/files/{file_id}",
                description="Download file content. Always sends alt=media.",
                category="download",
                permissions=("network", "filesystem"),
                scopes=(read,),
                query=("alt", "acknowledgeAbuse", "supportsAllDrives"),
            ),
            OperationSpec(
                name="files.create",
                method="POST",
                path="/drive/v3/files",
                description=(
                    "Create a file or folder from metadata. For a folder, set "
                    "mimeType to application/vnd.google-apps.folder."
                ),
                category="write",
                permissions=_NET,
                scopes=(file_scope,),
                query=("fields", "supportsAllDrives"),
                body=("name", "mimeType", "parents", "description", "properties"),
                required=("name",),
            ),
            OperationSpec(
                name="files.upload",
                method="POST",
                path="/upload/drive/v3/files",
                description=(
                    "Simple upload (uploadType=media). Correct up to 5 MB; larger "
                    "files need Drive's resumable protocol, which this platform "
                    "does not implement."
                ),
                category="upload",
                permissions=("network", "filesystem"),
                scopes=(file_scope,),
                query=("uploadType", "fields", "supportsAllDrives"),
                body=("name", "mimeType", "parents"),
            ),
            OperationSpec(
                name="files.update",
                method="PATCH",
                path="/drive/v3/files/{file_id}",
                description=("Rename or edit metadata. Moving is addParents/removeParents."),
                category="write",
                permissions=_NET,
                scopes=(file_scope,),
                query=("addParents", "removeParents", "fields", "supportsAllDrives"),
                body=("name", "description", "mimeType", "trashed", "properties"),
            ),
            OperationSpec(
                name="files.delete",
                method="DELETE",
                path="/drive/v3/files/{file_id}",
                description="Permanently delete a file. Trashing is files.update(trashed=true).",
                category="write",
                permissions=_NET,
                scopes=(file_scope,),
                query=("supportsAllDrives",),
            ),
            OperationSpec(
                name="files.copy",
                method="POST",
                path="/drive/v3/files/{file_id}/copy",
                description="Copy a file.",
                category="write",
                permissions=_NET,
                scopes=(file_scope,),
                query=("fields", "supportsAllDrives"),
                body=("name", "parents"),
            ),
            OperationSpec(
                name="permissions.list",
                method="GET",
                path="/drive/v3/files/{file_id}/permissions",
                description="Who can see a file.",
                category="read",
                permissions=_NET,
                scopes=(metadata,),
                query=("fields", "pageSize", "supportsAllDrives"),
            ),
            OperationSpec(
                name="permissions.create",
                method="POST",
                path="/drive/v3/files/{file_id}/permissions",
                description="Share a file with a user, group, domain or anyone.",
                category="admin",
                permissions=_NET,
                scopes=(file_scope,),
                query=("sendNotificationEmail", "transferOwnership", "supportsAllDrives"),
                body=("role", "type", "emailAddress", "domain"),
                required=("role", "type"),
            ),
            OperationSpec(
                name="permissions.delete",
                method="DELETE",
                path="/drive/v3/files/{file_id}/permissions/{permission_id}",
                description="Revoke a share.",
                category="admin",
                permissions=_NET,
                scopes=(file_scope,),
                query=("supportsAllDrives",),
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Docs / Sheets / Slides
# ---------------------------------------------------------------------------
def docs_spec() -> IntegrationSpec:
    docs = "https://www.googleapis.com/auth/documents"
    docs_read = "https://www.googleapis.com/auth/documents.readonly"

    return IntegrationSpec(
        integration_id="google_docs",
        name="Google Docs",
        vendor="google",
        description="Create, read and edit Google Docs documents.",
        base_url="https://docs.googleapis.com",
        auth=google_auth(docs_read),
        tags=("documents",),
        operations=(
            OperationSpec(
                name="documents.create",
                method="POST",
                path="/v1/documents",
                description="Create an empty document with a title.",
                category="write",
                permissions=_NET,
                scopes=(docs,),
                body=("title",),
                required=("title",),
            ),
            OperationSpec(
                name="documents.get",
                method="GET",
                path="/v1/documents/{document_id}",
                description="Fetch a document's full structured content.",
                category="read",
                permissions=_NET,
                scopes=(docs_read,),
                query=("suggestionsViewMode",),
            ),
            OperationSpec(
                name="documents.batch_update",
                method="POST",
                path="/v1/documents/{document_id}:batchUpdate",
                description=(
                    "Apply edits: insertText, deleteContentRange, updateTextStyle, "
                    "createParagraphBullets. Comments are Drive's API, not this one."
                ),
                category="write",
                permissions=_NET,
                scopes=(docs,),
                body=("requests", "writeControl"),
                required=("requests",),
            ),
        ),
    )


def sheets_spec() -> IntegrationSpec:
    sheets = "https://www.googleapis.com/auth/spreadsheets"
    sheets_read = "https://www.googleapis.com/auth/spreadsheets.readonly"

    return IntegrationSpec(
        integration_id="google_sheets",
        name="Google Sheets",
        vendor="google",
        description="Read and write spreadsheet values, formulas and charts.",
        base_url="https://sheets.googleapis.com",
        auth=google_auth(sheets_read),
        tags=("spreadsheets",),
        operations=(
            OperationSpec(
                name="spreadsheets.create",
                method="POST",
                path="/v4/spreadsheets",
                description="Create a spreadsheet.",
                category="write",
                permissions=_NET,
                scopes=(sheets,),
                body=("properties", "sheets"),
            ),
            OperationSpec(
                name="spreadsheets.get",
                method="GET",
                path="/v4/spreadsheets/{spreadsheet_id}",
                description="Spreadsheet metadata, sheets and (optionally) grid data.",
                category="read",
                permissions=_NET,
                scopes=(sheets_read,),
                query=("includeGridData", "ranges", "fields"),
            ),
            OperationSpec(
                name="values.get",
                method="GET",
                path="/v4/spreadsheets/{spreadsheet_id}/values/{range}",
                description="Read a cell range in A1 notation.",
                category="read",
                permissions=_NET,
                scopes=(sheets_read,),
                query=("majorDimension", "valueRenderOption", "dateTimeRenderOption"),
            ),
            OperationSpec(
                name="values.update",
                method="PUT",
                path="/v4/spreadsheets/{spreadsheet_id}/values/{range}",
                description=(
                    "Write a cell range. valueInputOption=USER_ENTERED makes '=SUM(A1:A9)' "
                    "a formula; RAW makes it text."
                ),
                category="write",
                permissions=_NET,
                scopes=(sheets,),
                query=("valueInputOption", "includeValuesInResponse"),
                body=("values", "majorDimension", "range"),
                required=("values", "valueInputOption"),
            ),
            OperationSpec(
                name="values.append",
                method="POST",
                path="/v4/spreadsheets/{spreadsheet_id}/values/{range}:append",
                description="Append rows after the last row of a range -- CSV import lands here.",
                category="write",
                permissions=_NET,
                scopes=(sheets,),
                query=("valueInputOption", "insertDataOption"),
                body=("values", "majorDimension"),
                required=("values", "valueInputOption"),
            ),
            OperationSpec(
                name="spreadsheets.batch_update",
                method="POST",
                path="/v4/spreadsheets/{spreadsheet_id}:batchUpdate",
                description=(
                    "Structural edits: addChart, addSheet, repeatCell, sort. Charts "
                    "and reports are built here."
                ),
                category="write",
                permissions=_NET,
                scopes=(sheets,),
                body=("requests", "includeSpreadsheetInResponse"),
                required=("requests",),
            ),
        ),
    )


def slides_spec() -> IntegrationSpec:
    slides = "https://www.googleapis.com/auth/presentations"
    slides_read = "https://www.googleapis.com/auth/presentations.readonly"

    return IntegrationSpec(
        integration_id="google_slides",
        name="Google Slides",
        vendor="google",
        description="Create and edit presentations, layouts and speaker notes.",
        base_url="https://slides.googleapis.com",
        auth=google_auth(slides_read),
        tags=("presentations",),
        operations=(
            OperationSpec(
                name="presentations.create",
                method="POST",
                path="/v1/presentations",
                description="Create a presentation.",
                category="write",
                permissions=_NET,
                scopes=(slides,),
                body=("title",),
                required=("title",),
            ),
            OperationSpec(
                name="presentations.get",
                method="GET",
                path="/v1/presentations/{presentation_id}",
                description="Fetch a presentation, its slides and its layouts.",
                category="read",
                permissions=_NET,
                scopes=(slides_read,),
            ),
            OperationSpec(
                name="presentations.batch_update",
                method="POST",
                path="/v1/presentations/{presentation_id}:batchUpdate",
                description=(
                    "Apply edits: createSlide (with a predefined layout), insertText, "
                    "createShape. Speaker notes are text on the notes page."
                ),
                category="write",
                permissions=_NET,
                scopes=(slides,),
                body=("requests", "writeControl"),
                required=("requests",),
            ),
            OperationSpec(
                name="pages.get",
                method="GET",
                path="/v1/presentations/{presentation_id}/pages/{page_object_id}",
                description="One slide or notes page.",
                category="read",
                permissions=_NET,
                scopes=(slides_read,),
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Contacts / Tasks / Keep / Photos
# ---------------------------------------------------------------------------
def contacts_spec() -> IntegrationSpec:
    read = "https://www.googleapis.com/auth/contacts.readonly"
    write = "https://www.googleapis.com/auth/contacts"

    return IntegrationSpec(
        integration_id="google_contacts",
        name="Google Contacts",
        vendor="google",
        description="Search, read and manage contacts through the People API.",
        base_url="https://people.googleapis.com",
        auth=google_auth(read),
        tags=("contacts",),
        search_operation="people.search",
        operations=(
            OperationSpec(
                name="people.list",
                method="GET",
                path="/v1/people/me/connections",
                description="List this account's contacts.",
                category="read",
                permissions=_NET,
                scopes=(read,),
                query=("pageSize", "pageToken", "personFields", "sortOrder"),
                required=("personFields",),
            ),
            OperationSpec(
                name="people.search",
                method="GET",
                path="/v1/people:searchContacts",
                description="Search contacts by name, email or phone.",
                category="search",
                permissions=_NET,
                scopes=(read,),
                query=("query", "pageSize", "readMask"),
                required=("query", "readMask"),
            ),
            OperationSpec(
                name="people.get",
                method="GET",
                path="/v1/people/{resource_name}",
                description="One contact. resource_name looks like 'people/c123'.",
                category="read",
                permissions=_NET,
                scopes=(read,),
                query=("personFields",),
                required=("personFields",),
            ),
            OperationSpec(
                name="people.create",
                method="POST",
                path="/v1/people:createContact",
                description="Create a contact.",
                category="write",
                permissions=_NET,
                scopes=(write,),
                query=("personFields",),
                body=("names", "emailAddresses", "phoneNumbers", "organizations", "biographies"),
            ),
            OperationSpec(
                name="people.update",
                method="PATCH",
                path="/v1/people/{resource_name}:updateContact",
                description="Update a contact. updatePersonFields names what changed.",
                category="write",
                permissions=_NET,
                scopes=(write,),
                query=("updatePersonFields", "personFields"),
                body=("names", "emailAddresses", "phoneNumbers", "organizations", "etag"),
                required=("updatePersonFields",),
            ),
            OperationSpec(
                name="people.delete",
                method="DELETE",
                path="/v1/people/{resource_name}:deleteContact",
                description="Delete a contact.",
                category="write",
                permissions=_NET,
                scopes=(write,),
            ),
        ),
    )


def tasks_spec() -> IntegrationSpec:
    read = "https://www.googleapis.com/auth/tasks.readonly"
    write = "https://www.googleapis.com/auth/tasks"

    return IntegrationSpec(
        integration_id="google_tasks",
        name="Google Tasks",
        vendor="google",
        description=(
            "Read and write Google Tasks. Import into JARVIS tasks is one-directional "
            "-- see the availability note."
        ),
        base_url=_GOOGLE_APIS,
        auth=google_auth(read),
        tags=("tasks", "productivity"),
        availability_note=(
            "Two-way sync with JARVIS tasks is not implemented: it needs a conflict "
            "policy and a scheduler to run it, and M7 Phase 6 has not shipped. These "
            "operations read and write Google Tasks directly; importing them into the "
            "JARVIS task domain is a caller-side copy, not a synchronized mirror."
        ),
        operations=(
            OperationSpec(
                name="tasklists.list",
                method="GET",
                path="/tasks/v1/users/@me/lists",
                description="List task lists.",
                category="read",
                permissions=_NET,
                scopes=(read,),
                query=("maxResults", "pageToken"),
            ),
            OperationSpec(
                name="tasks.list",
                method="GET",
                path="/tasks/v1/lists/{tasklist}/tasks",
                description="List tasks in a list.",
                category="read",
                permissions=_NET,
                scopes=(read,),
                query=(
                    "maxResults",
                    "pageToken",
                    "showCompleted",
                    "showHidden",
                    "dueMin",
                    "dueMax",
                    "updatedMin",
                ),
            ),
            OperationSpec(
                name="tasks.insert",
                method="POST",
                path="/tasks/v1/lists/{tasklist}/tasks",
                description="Create a task.",
                category="write",
                permissions=_NET,
                scopes=(write,),
                query=("parent", "previous"),
                body=("title", "notes", "due", "status"),
                required=("title",),
            ),
            OperationSpec(
                name="tasks.patch",
                method="PATCH",
                path="/tasks/v1/lists/{tasklist}/tasks/{task_id}",
                description="Update a task -- completing one is status=completed.",
                category="write",
                permissions=_NET,
                scopes=(write,),
                body=("title", "notes", "due", "status", "completed"),
            ),
            OperationSpec(
                name="tasks.delete",
                method="DELETE",
                path="/tasks/v1/lists/{tasklist}/tasks/{task_id}",
                description="Delete a task.",
                category="write",
                permissions=_NET,
                scopes=(write,),
            ),
        ),
    )


def keep_spec() -> IntegrationSpec:
    read = "https://www.googleapis.com/auth/keep.readonly"
    write = "https://www.googleapis.com/auth/keep"

    return IntegrationSpec(
        integration_id="google_keep",
        name="Google Keep",
        vendor="google",
        description="Read and create Keep notes (Google Workspace accounts only).",
        base_url="https://keep.googleapis.com",
        auth=google_auth(read),
        tags=("notes",),
        availability_note=(
            "The Keep API serves Google Workspace accounts with the Keep API enabled by "
            "an administrator; it does not serve consumer @gmail.com accounts. Two-way "
            "sync with JARVIS workspace notes is not implemented -- it needs a conflict "
            "policy and a scheduler (M7 Phase 6)."
        ),
        operations=(
            OperationSpec(
                name="notes.list",
                method="GET",
                path="/v1/notes",
                description="List notes.",
                category="read",
                permissions=("network", "memory.read"),
                scopes=(read,),
                query=("pageSize", "pageToken", "filter"),
            ),
            OperationSpec(
                name="notes.get",
                method="GET",
                path="/v1/{name}",
                description="One note. 'name' looks like 'notes/abc123'.",
                category="read",
                permissions=("network", "memory.read"),
                scopes=(read,),
            ),
            OperationSpec(
                name="notes.create",
                method="POST",
                path="/v1/notes",
                description="Create a note.",
                category="write",
                permissions=("network", "memory.write"),
                scopes=(write,),
                body=("title", "body"),
                required=("title",),
            ),
            OperationSpec(
                name="notes.delete",
                method="DELETE",
                path="/v1/{name}",
                description="Delete a note.",
                category="write",
                permissions=("network", "memory.write"),
                scopes=(write,),
            ),
        ),
    )


def photos_spec() -> IntegrationSpec:
    read = "https://www.googleapis.com/auth/photoslibrary.readonly"

    return IntegrationSpec(
        integration_id="google_photos",
        name="Google Photos",
        vendor="google",
        description="Browse albums and search media items by date, content or type.",
        base_url="https://photoslibrary.googleapis.com",
        auth=google_auth(read),
        tags=("photos", "media"),
        search_operation="media.search",
        operations=(
            OperationSpec(
                name="albums.list",
                method="GET",
                path="/v1/albums",
                description="List albums.",
                category="read",
                permissions=_NET,
                scopes=(read,),
                query=("pageSize", "pageToken", "excludeNonAppCreatedData"),
            ),
            OperationSpec(
                name="albums.get",
                method="GET",
                path="/v1/albums/{album_id}",
                description="One album's metadata.",
                category="read",
                permissions=_NET,
                scopes=(read,),
            ),
            OperationSpec(
                name="media.search",
                method="POST",
                path="/v1/mediaItems:search",
                description=(
                    "Search media items by album, date range or content category. "
                    "Photos has no free-text search; filters are the query language."
                ),
                category="search",
                permissions=_NET,
                scopes=(read,),
                body=("albumId", "filters", "pageSize", "pageToken", "orderBy"),
            ),
            OperationSpec(
                name="media.get",
                method="GET",
                path="/v1/mediaItems/{media_item_id}",
                description="One media item, with its baseUrl and metadata.",
                category="read",
                permissions=_NET,
                scopes=(read,),
            ),
        ),
    )


#: Every Google Workspace spec this build ships, by integration id.
#:
#: A plain mapping of builders rather than a registry class: the live
#: providers live in M10.5's ``MCPProviderRegistry``, and a second
#: registry for the *declarations* would be the parallel system this
#: task group is forbidden to build. Discovery of installed integrations
#: is ``MCPProviderRegistry.discover``; this is only "what could be
#: installed".
GOOGLE_SPECS: dict[str, Callable[[], IntegrationSpec]] = {
    "google_gmail": gmail_spec,
    "google_calendar": calendar_spec,
    "google_meet": meet_spec,
    "google_drive": drive_spec,
    "google_docs": docs_spec,
    "google_sheets": sheets_spec,
    "google_slides": slides_spec,
    "google_contacts": contacts_spec,
    "google_tasks": tasks_spec,
    "google_keep": keep_spec,
    "google_photos": photos_spec,
}
