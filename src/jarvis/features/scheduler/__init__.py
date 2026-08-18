"""Scheduler MVP internals -- Milestone 7 Phase 6.

Mirrors ``features/automation/``'s own layering: this package holds the
Scheduler's internal components; ``services/schedule_service.py`` composes
them into the single, DI-registered orchestration entry point, the same
split ``AutomationService`` already established for the automation engine.
"""
