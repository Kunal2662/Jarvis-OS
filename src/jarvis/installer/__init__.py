"""The Universal Installer -- Milestone 22 Task Group A.

**Isolated by construction.** Nothing in this package imports a service,
a repository, the DI container, a route or a database model, and nothing
outside it imports *from* it. It has to be that way: the installer runs
*before* JARVIS is installed, on a machine where none of those things
exist yet. That isolation is also what keeps this milestone inside the
architecture freeze -- the package is purely additive, adds no REST
route, touches no schema, and changes no contract.

The React installer UI reaches this code through a **CLI that emits
JSON** (``python -m jarvis.installer``), not through the API. An
installer cannot call an API served by the application it is installing,
and adding a route for it would have meant modifying frozen contracts.

**Nothing here fabricates a measurement.** Every field this package
reports is either read from the machine or is ``None``. A GPU that
cannot be probed is ``None``, not "Unknown GPU"; a temperature sensor
Windows does not expose is ``None``, not a plausible 45°C. An installer
that guesses at hardware produces a calibration that is wrong in ways
the user cannot see, which is worse than admitting the gap -- so
`AICalibration` records which inputs were actually available and says so
in the UI.
"""

from jarvis.installer.calibration import (
    AICalibration,
    CalibrationInputs,
    calibrate,
)
from jarvis.installer.hardware import (
    CpuInfo,
    GpuInfo,
    HardwareProfile,
    MemoryInfo,
    PowerInfo,
    StorageInfo,
    detect_hardware,
)
from jarvis.installer.local_model import (
    MODEL_TIERS,
    ModelTier,
    recommend_model,
)
from jarvis.installer.validation import (
    ValidationReport,
    ValidationResult,
    validate_installation,
)
from jarvis.installer.voice import VoicePlan, plan_voice

__all__ = [
    "MODEL_TIERS",
    "AICalibration",
    "CalibrationInputs",
    "CpuInfo",
    "GpuInfo",
    "HardwareProfile",
    "MemoryInfo",
    "ModelTier",
    "PowerInfo",
    "StorageInfo",
    "ValidationReport",
    "ValidationResult",
    "VoicePlan",
    "calibrate",
    "detect_hardware",
    "plan_voice",
    "recommend_model",
    "validate_installation",
]
