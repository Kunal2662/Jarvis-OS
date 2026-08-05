"""AI Workspace domain models -- Milestone 11 Task Group D.

The pure half of the AI layer over the workspace substrate Task Groups
A-C shipped: the closed vocabularies, the value objects a workspace
context is made of, the packing that fits one inside a character budget,
and the prompt construction the assistant hands to an LLM. No database,
no service, no container -- every function here is total, deterministic
and testable on its own, the same posture ``domain/files/models.py``
took for path safety.

**Why a character budget at all.** ``WorkspaceManager.context`` already
returns a workspace's projects, notes and neighbouring hits, and Task
Groups B and C added tasks, calendars, reminders and files on top. Sent
to a model verbatim, a busy workspace's context is unbounded -- it grows
with the user's data, and the first symptom of that is not a truncated
answer but a rejected request or a silently dropped tail. Budgeting
here, in a pure function, makes the truncation a *decision* the payload
reports (``ContextSection.truncated``, ``WorkspaceContext.used_chars``)
rather than something a provider does invisibly at the boundary.

**Why sections are ordered rather than scored.** The order in
:data:`SECTION_ORDER` is a fixed editorial judgement -- what the
workspace *is*, then what is overdue, then what is coming, then the
material -- not a relevance ranking. A learned ordering would need
training signal this milestone does not have, and pretending otherwise
by inventing weights would be the overstatement Task Group C's indexing
note set out to avoid. When the budget runs out, the tail is what is
dropped, and the caller can see exactly which sections lost items.

**Tokens are not counted here.** The budget is in characters, because
tokenization belongs to a provider and this module has no provider.
Characters are a stable, provider-independent proxy; a caller that
needs a token-exact bound converts once, at the boundary that knows
which model it is talking to.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

#: The sections a workspace context is assembled from, in the order they
#: are rendered and the order the budget consumes them. Fixed rather
#: than configurable: a caller reordering these would change what gets
#: dropped under pressure, which is a product decision and not a knob.
SECTION_ORDER: tuple[str, ...] = (
    "workspace",
    "projects",
    "tasks",
    "calendar",
    "reminders",
    "notes",
    "files",
    "knowledge",
    "memories",
)

#: Membership test for the above. A section name outside this set is a
#: programming error, not user input, and is rejected rather than
#: rendered into a prompt under a name nothing recognises.
CONTEXT_SECTIONS: frozenset[str] = frozenset(SECTION_ORDER)

#: What a knowledge link can point at. Four narrow targets plus the
#: workspace itself, which is the default rather than a degenerate case
#: -- the same convention ``WorkspaceAttachment`` established.
#:
#: Deliberately *not* the same five as attachments. An attachment says
#: "this file belongs here" and can hang off anything; a knowledge link
#: says "this text is about this entity", so it only exists for entities
#: that carry prose. Calendar events and reminders are excluded for that
#: reason and one more: an event's workspace is owned by its calendar,
#: so the row could not carry a workspace foreign key that agrees with
#: itself without a join.
LINK_TARGETS: frozenset[str] = frozenset({"workspace", "project", "note", "task", "file"})

#: How a link came to exist. ``extracted`` means the knowledge graph
#: produced it from the target's own text; ``manual`` means a caller
#: asserted it. Kept apart because a later re-ingestion may legitimately
#: replace everything it extracted and must not touch what a human said.
LINK_SOURCES: frozenset[str] = frozenset({"extracted", "manual"})

#: What the assistant can be asked to do. Three modes rather than one
#: free-form prompt, because each one grounds differently: ``ask``
#: retrieves against the question, ``summarize`` and ``next_actions``
#: retrieve against nothing and read the context alone.
ASSIST_MODES: frozenset[str] = frozenset({"summarize", "ask", "next_actions"})

#: Default budget for one assembled context. Roughly a page and a half
#: of prose -- large enough that a normal workspace fits whole, small
#: enough to leave room for the question and the answer in any
#: context window this project's providers offer.
DEFAULT_CONTEXT_BUDGET_CHARS = 6000

#: A budget below this cannot hold a workspace header plus one item, so
#: it is raised rather than honoured -- an empty context is a worse
#: answer than a small one.
MIN_CONTEXT_BUDGET_CHARS = 200

#: Per-item clip. One long note must not consume the whole budget and
#: starve every section after it.
DEFAULT_ITEM_CHARS = 240

#: How many items any one section contributes before packing. A cap on
#: input, distinct from the budget's cap on output: without it, a
#: workspace with 4,000 tasks would build 4,000 objects to discard
#: 3,990 of them.
DEFAULT_SECTION_ITEMS = 10

_ELLIPSIS = "..."


def clip(text: str, limit: int) -> str:
    """Trim *text* to *limit* characters, marking that it was trimmed.

    ASCII ellipsis on purpose: this string is rendered into prompts and
    JSON, and a codepoint that looks like three dots in one editor and a
    box in another is a difference no reader can act on.
    """
    text = " ".join((text or "").split())
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if limit <= len(_ELLIPSIS):
        return text[:limit]
    return text[: limit - len(_ELLIPSIS)].rstrip() + _ELLIPSIS


@dataclass(frozen=True, slots=True)
class ContextItem:
    """One line of context: a thing, optionally what about it, and where
    it lives. ``uri`` mirrors ``SearchResult.uri`` so a caller can link
    straight to the entity a line came from."""

    title: str
    detail: str = ""
    uri: str = ""

    def render(self, *, item_chars: int = DEFAULT_ITEM_CHARS) -> str:
        title = clip(self.title, item_chars)
        if not self.detail:
            return f"- {title}"
        remaining = item_chars - len(title) - 3
        detail = clip(self.detail, max(remaining, 0))
        return f"- {title} -- {detail}" if detail else f"- {title}"

    def as_dict(self) -> dict[str, Any]:
        return {"title": self.title, "detail": self.detail, "uri": self.uri}


@dataclass(frozen=True, slots=True)
class ContextSection:
    """One named group of items.

    ``total`` is how many items the owning subsystem reported *before*
    any capping or packing, which is what makes truncation visible: a
    section holding three of forty tasks says so, instead of looking
    like a workspace with three tasks.
    """

    name: str
    items: tuple[ContextItem, ...] = ()
    total: int = 0

    @property
    def truncated(self) -> bool:
        return self.total > len(self.items)

    def render(self, *, item_chars: int = DEFAULT_ITEM_CHARS) -> str:
        """Empty sections render as the empty string rather than a bare
        heading -- a prompt full of "Notes:" with nothing under it
        teaches a model that this workspace has headings, not notes."""
        if not self.items:
            return ""
        lines = [f"{self.name.capitalize()}:"]
        lines.extend(item.render(item_chars=item_chars) for item in self.items)
        if self.truncated:
            lines.append(f"  (+{self.total - len(self.items)} more)")
        return "\n".join(lines)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "items": [item.as_dict() for item in self.items],
            "total": self.total,
            "truncated": self.truncated,
        }


@dataclass(frozen=True, slots=True)
class WorkspaceContext:
    """A packed, ordered, budgeted view of one workspace.

    The object the assistant prompts from and the REST layer serialises,
    so the two can never disagree about what the model was shown.
    """

    workspace_id: str
    #: Carried on the context rather than dug back out of the
    #: ``workspace`` section's first item, because the assistant's prompt
    #: needs it and parsing a rendered line to recover a field the
    #: builder had is how a renderer becomes an accidental format.
    workspace_name: str = ""
    sections: tuple[ContextSection, ...] = ()
    budget_chars: int = DEFAULT_CONTEXT_BUDGET_CHARS
    used_chars: int = 0
    dropped_sections: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_empty(self) -> bool:
        return not any(section.items for section in self.sections)

    @property
    def truncated_sections(self) -> tuple[str, ...]:
        return tuple(section.name for section in self.sections if section.truncated)

    def section(self, name: str) -> ContextSection | None:
        for section in self.sections:
            if section.name == name:
                return section
        return None

    def render(self, *, item_chars: int = DEFAULT_ITEM_CHARS) -> str:
        blocks = [section.render(item_chars=item_chars) for section in self.sections]
        return "\n\n".join(block for block in blocks if block)

    def as_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "workspace_name": self.workspace_name,
            "sections": [section.as_dict() for section in self.sections],
            "budget_chars": self.budget_chars,
            "used_chars": self.used_chars,
            "truncated_sections": list(self.truncated_sections),
            "dropped_sections": list(self.dropped_sections),
            "text": self.render(),
        }


def order_sections(sections: Sequence[ContextSection]) -> tuple[ContextSection, ...]:
    """Sorts into :data:`SECTION_ORDER`. A name outside the vocabulary
    sorts last rather than raising -- this is a rendering helper, and
    losing a section silently would be worse than showing it late."""
    index = {name: position for position, name in enumerate(SECTION_ORDER)}
    return tuple(sorted(sections, key=lambda s: index.get(s.name, len(SECTION_ORDER))))


def pack(
    sections: Sequence[ContextSection],
    *,
    workspace_id: str,
    workspace_name: str = "",
    budget_chars: int = DEFAULT_CONTEXT_BUDGET_CHARS,
    item_chars: int = DEFAULT_ITEM_CHARS,
) -> WorkspaceContext:
    """Fit *sections* into *budget_chars*, in :data:`SECTION_ORDER`.

    Greedy and in order: each section takes what it can, and the first
    item that would exceed the budget ends the packing. Later sections
    keep their ``total`` with no items, which is how the payload reports
    "there is more here than you were shown" instead of implying an
    empty workspace.

    Greedy rather than proportional because the ordering already encodes
    the priority: dividing the budget evenly would starve the workspace
    header to make room for the ninth memory, which is exactly backwards.
    """
    budget = max(budget_chars, MIN_CONTEXT_BUDGET_CHARS)
    used = 0
    packed: list[ContextSection] = []
    dropped: list[str] = []

    for section in order_sections(sections):
        kept: list[ContextItem] = []
        header_cost = len(section.name) + 2
        for item in section.items:
            cost = len(item.render(item_chars=item_chars)) + 1
            if not kept:
                cost += header_cost
            if used + cost > budget:
                break
            used += cost
            kept.append(item)
        if section.items and not kept:
            dropped.append(section.name)
        packed.append(ContextSection(name=section.name, items=tuple(kept), total=section.total))

    return WorkspaceContext(
        workspace_id=workspace_id,
        workspace_name=workspace_name,
        sections=tuple(packed),
        budget_chars=budget,
        used_chars=used,
        dropped_sections=tuple(dropped),
    )


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------
#: One instruction per mode. Written here, in the domain, rather than
#: inline in the service, for the same reason
#: ``agents/nodes/responder.build_final_response_prompt`` is a shared
#: function: two call sites composing "the same" prompt separately drift,
#: and a prompt that drifts changes answers without changing any test.
_MODE_INSTRUCTIONS: dict[str, str] = {
    "summarize": (
        "Summarize the state of this workspace for its owner. Cover what "
        "is in progress, what is overdue and what is coming up. Be brief "
        "and concrete."
    ),
    "ask": (
        "Answer the question using only the workspace context below. If "
        "the context does not contain the answer, say so plainly rather "
        "than guessing."
    ),
    "next_actions": (
        "Propose the next actions for this workspace, most urgent first. "
        "Base every suggestion on something in the context below and say "
        "which item it comes from. Do not invent work that is not there."
    ),
}

_GROUNDING_RULE = (
    "You are assisting inside one workspace. Everything you may rely on "
    "is in the context below; it is the whole of what you can see. Do "
    "not invent entities, dates or files that do not appear in it."
)


def build_assist_prompt(
    *,
    mode: str,
    workspace_name: str,
    context_text: str,
    retrieved_text: str = "",
    question: str = "",
) -> str:
    """Assemble the grounded prompt for one assist call.

    Pure: no service, no LLM, no clock. That is what lets the prompt
    itself be asserted in a test rather than inferred from whatever the
    model happened to answer.
    """
    instruction = _MODE_INSTRUCTIONS.get(mode, _MODE_INSTRUCTIONS["summarize"])
    parts = [_GROUNDING_RULE, "", instruction, "", f"Workspace: {workspace_name}"]
    if question:
        parts += ["", f"Question: {question}"]
    parts += ["", "Context:", context_text or "(no workspace context available)"]
    if retrieved_text:
        parts += ["", "Retrieved for this question:", retrieved_text]
    return "\n".join(parts)


def render_results(
    rows: Sequence[tuple[str, str, str]], *, item_chars: int = DEFAULT_ITEM_CHARS
) -> str:
    """Renders ``(source, title, content)`` triples as context lines.

    Takes tuples rather than ``SearchResult`` so this module keeps
    importing nothing from ``core.interfaces`` -- the domain layer
    describes shapes, it does not depend on the ports the services wire
    together.
    """
    return "\n".join(
        ContextItem(title=f"[{source}] {title}", detail=content).render(item_chars=item_chars)
        for source, title, content in rows
    )
