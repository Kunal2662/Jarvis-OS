"""Core layer — framework-agnostic abstractions the entire app depends on.

Only the following imports are allowed inside ``jarvis.core``:

* the standard library
* ``pydantic`` / ``pydantic-settings``
* ``loguru`` / ``structlog``
* ``dependency_injector``

No ``PySide6``, no ``fastapi``, no infrastructure adapter, no ``langgraph``.
This isolation is what keeps the codebase testable and swappable.
"""
