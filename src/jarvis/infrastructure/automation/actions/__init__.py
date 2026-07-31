"""Concrete, per-action implementations dispatched by the executor.

Each action is its own small class (per the milestone spec) implementing
:class:`jarvis.infrastructure.automation.actions.base.BaseAction`. Look up
an instance by :class:`~jarvis.domain.automation.ActionType` via
:func:`jarvis.infrastructure.automation.actions.registry.get_action`.
"""

from __future__ import annotations
