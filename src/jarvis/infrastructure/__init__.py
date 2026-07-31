"""Infrastructure layer — concrete adapters for every port in ``core.interfaces``.

Each subpackage implements exactly one port. Adapters are the *only* place
where third-party libraries (``openai``, ``ollama``, ``chromadb``, ``sqlalchemy``,
``playwright``, ``pywinauto``, ``whisper`` …) may be imported.
"""
