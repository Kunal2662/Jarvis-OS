"""Task planner -- turns one natural-language instruction into an ExecutionPlan.

Splits multi-step instructions ("Create folder Work. Download image. Move
image into folder.") into individual :class:`Intent`s via the
:class:`~jarvis.features.automation.parser.IntentParser`, then chains them
into a :class:`Step` sequence. Steps are sequential (each depends on the
previous one) by default -- this is the simplest correct behaviour and
matches the milestone brief's worked example. A line containing
"at the same time" / "simultaneously" / "in parallel" is *not* chained to
the previous step, so independent steps can run concurrently in the
executor.
"""

from __future__ import annotations

import re

from jarvis.domain.automation.models import ExecutionPlan, Step
from jarvis.features.automation.parser import IntentParser

_LINE_SPLIT = re.compile(r"\r?\n|(?:,?\s+then\s+)|;\s*|(?:\s+and\s+then\s+)", re.IGNORECASE)
_PARALLEL_MARKERS = re.compile(
    r"\b(at the same time|simultaneously|in parallel|meanwhile)\b", re.IGNORECASE
)


class TaskPlanner:
    def __init__(self, parser: IntentParser | None = None, *, default_max_retries: int = 0) -> None:
        self._parser = parser or IntentParser()
        self._default_max_retries = default_max_retries

    def split_instructions(self, text: str) -> list[str]:
        parts = [p.strip() for p in _LINE_SPLIT.split(text) if p and p.strip()]
        return parts or ([text.strip()] if text.strip() else [])

    def build_plan(self, text: str, *, max_retries: int | None = None) -> ExecutionPlan:
        lines = self.split_instructions(text)
        intents = self._parser.parse_many(lines)

        plan = ExecutionPlan(raw_text=text)
        previous_step_id: str | None = None
        retries = self._default_max_retries if max_retries is None else max_retries

        for line, intent in zip(lines, intents, strict=False):
            args = dict(intent.arguments)
            if intent.target is not None and "target" not in args:
                args["target"] = intent.target

            parallel = bool(_PARALLEL_MARKERS.search(line))
            depends_on = [] if (parallel or previous_step_id is None) else [previous_step_id]

            step = Step(
                action=intent.action,
                args=args,
                depends_on=depends_on,
                max_retries=retries,
                label=line,
            )
            plan.steps.append(step)
            previous_step_id = step.id

        return plan
