"""Developer Platform Tools (Milestone 9 Task Group E).

Real, working backend components behind Developer Mode's tooling --
Debug Console + Live Logs (``debug_console.py``), Performance Profiler
(``performance_profiler.py``), State Inspector (``state_inspector.py``),
API Inspector (``api_inspector.py``). Each is a thin, focused wrapper
around real, already-shipped M9 infrastructure (the loguru log stream,
``HealthMonitor``'s poll ticks, ``ServiceManager``/``PluginRegistry``'s
own state, this app's own FastAPI request/response cycle) -- this
package adds bounded history/filtering/query surfaces over data that
already exists, not a second, parallel data source.

Exposed over REST by ``infrastructure/api/routes/devtools.py`` -- see
``docs/MASTER_ROADMAP.md`` section 8 M9's Developer Platform Tools
module and ``docs/ARCHITECTURE.md`` section 6 for the "Plugin Marketplace
Foundation" and "Debug Console"/"Live Logs" design this package
implements.
"""

from __future__ import annotations
