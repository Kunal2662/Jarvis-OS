"""Shared pagination -- Milestone 11 Task Group F.

One convention for every collection route, rather than a limit
parameter invented per router.

**The defect this closes.** Every repository in this codebase already
caps its queries (``limit: int = 200`` on the workspace tables, ``500``
on files and links). Nothing above them exposed that cap, and the
response envelope reported only ``count`` -- so a workspace holding 250
notes returned 200 of them, said ``"count": 200``, and gave the caller
no way to tell a complete answer from a truncated one, nor any way to
reach the remaining 50. The cap was right; its invisibility was the bug.

**Over-fetch by one, rather than a second COUNT query.** ``has_more`` is
answered by asking the repository for ``limit + 1`` rows and returning
``limit`` of them. A ``COUNT(*)`` beside every listing would double the
queries to report a number most callers do not use, and would still be
racy against a concurrent insert. One extra row is exact for the
question actually asked -- "is there a next page" -- and costs nothing.

**Offset, where ``ARCHITECTURE.md`` §5 specifies cursors -- a
deliberate, recorded divergence.** That section is right about the
general case: offset paging drifts when rows are inserted between two
reads. It is implemented as offset here anyway, for a specific reason.
A correct cursor needs a *stable, unique* sort key, and these
collections do not have one: notes order by ``pinned DESC,
updated_at DESC`` and tasks by due date, neither of which is unique, so
a cursor would need a composite ``(sort_key, id)`` tiebreaker designed
per collection. That is a real piece of work and it belongs with the
collection that first needs it -- a high-write feed -- rather than being
retrofitted across nine of a single user's own lists, where concurrent
insertion during paging is close to hypothetical.

What is *not* traded away is honesty about truncation: ``has_more`` is
exact regardless of drift, because it is answered by an over-fetched
row rather than by comparing against a total. When a collection needs
cursors, ``page_meta`` grows a ``next_cursor`` key and
``count``/``limit``/``has_more`` keep meaning exactly what they mean
now.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Query

#: What a caller gets without asking. Deliberately smaller than the
#: repository caps: a default that returns everything trains callers to
#: assume a listing is complete, which is the assumption this module
#: exists to break.
DEFAULT_LIMIT = 50

#: The most any single request may take. 200 is the number
#: ``docs/ARCHITECTURE.md`` §5 specifies, and it sits at or below every
#: repository's own cap -- so the API can never ask the storage layer
#: for more than it was built to return in one query.
MAX_LIMIT = 200


@dataclass(frozen=True, slots=True)
class Page:
    """One request's slice of a collection."""

    limit: int = DEFAULT_LIMIT
    offset: int = 0

    @property
    def probe_limit(self) -> int:
        """What to ask the repository for: one more than wanted, so the
        extra row's presence answers ``has_more`` exactly."""
        return self.limit + 1

    def trim(self, rows: list[Any]) -> tuple[list[Any], bool]:
        """``(page, has_more)`` -- drops the probe row when it arrived."""
        if len(rows) > self.limit:
            return rows[: self.limit], True
        return rows, False


def page_params(
    limit: int = Query(
        DEFAULT_LIMIT,
        ge=1,
        le=MAX_LIMIT,
        description=f"How many items to return (1-{MAX_LIMIT}).",
    ),
    offset: int = Query(0, ge=0, description="How many items to skip."),
) -> Page:
    """The ``Depends`` every collection route uses.

    Bounds are enforced by FastAPI rather than clamped silently: a
    caller asking for 10,000 gets a 422 naming the maximum, which is
    more useful than quietly receiving 500 and believing it was
    everything.
    """
    return Page(limit=limit, offset=offset)


def page_meta(*, page: Page, count: int, has_more: bool, **extra: Any) -> dict[str, Any]:
    """The ``meta`` block for a paginated collection.

    ``count`` keeps meaning what it always did -- how many items are in
    *this* response -- so no existing caller reading it breaks. The three
    new keys are additive.
    """
    return {
        "count": count,
        "limit": page.limit,
        "offset": page.offset,
        "has_more": has_more,
        **extra,
    }
