"""Plugin Platform (Milestone 9 Task Group D).

See ``docs/MASTER_ROADMAP.md`` section 8 M9's Plugin Platform module
and ``docs/ARCHITECTURE.md`` section 10 for the full design this
package implements: Plugin SDK (``sdk.py``, ``manifest.py``), Plugin
Loader (``loader.py``), Secure Plugin Sandbox (``sandbox.py``),
Extension API (``extension_api.py``), Permission Model
(``permissions.py``), Plugin Registration System (``registry.py``),
Plugin Store Foundation (``store.py``), Marketplace Foundation
(``marketplace.py``).

Universal Compatibility: this whole package is platform-neutral by
construction -- the only OS-specific code anywhere in it is behind
``core.interfaces.platform.IPlatformAdapter`` (Windows is the only
adapter implemented today; Linux/macOS are additional adapters, not a
redesign, when needed).
"""

from __future__ import annotations
