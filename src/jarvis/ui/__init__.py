"""PySide6 UI layer.

Only this package (and ``jarvis.main``) may import PySide6. Every widget
receives its dependencies via constructor injection; the DI container is
never accessed from inside a widget.
"""
