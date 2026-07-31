"""Feature modules (modular monolith).

Each feature is a self-contained slice that owns its models, view-models
(controllers) and views. Features may import services and events but never
touch infrastructure adapters directly.
"""
