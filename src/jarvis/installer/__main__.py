"""``python -m jarvis.installer`` -- the installer's data source.

**Why a CLI and not a REST route.** The installer runs before JARVIS is
installed, so there is no server to call; and adding a route would have
modified the frozen API contract. A JSON-emitting command is what an
installer front-end can actually invoke, and it keeps this milestone
additive.

Every command writes a single JSON document to stdout and nothing else,
so the caller can parse stdout without stripping log lines. Diagnostics
go to stderr.

    python -m jarvis.installer detect
    python -m jarvis.installer plan --account-type administrator
    python -m jarvis.installer validate --target "C:/Users/me/JARVIS"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from jarvis.installer.calibration import calibrate
from jarvis.installer.hardware import detect_hardware
from jarvis.installer.local_model import tier_to_dict
from jarvis.installer.validation import default_install_location, validate_installation
from jarvis.installer.voice import plan_voice

_EXIT_OK = 0
_EXIT_BLOCKED = 2
"""Validation found a blocking failure. Distinct from a crash (1) so a
front-end can tell "this machine cannot install" from "the probe
broke"."""


def _emit(payload: dict[str, Any]) -> None:
    json.dump(payload, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


def _detect(args: argparse.Namespace) -> int:
    target = Path(args.target) if args.target else default_install_location()
    profile = detect_hardware(target)
    _emit({"hardware": profile.to_dict()})
    return _EXIT_OK


def _plan(args: argparse.Namespace) -> int:
    """Detection, calibration, model recommendation and voice plan, in
    the shape the installer's Summary step renders.

    The payload is *shaped by account type*: a personal plan genuinely
    does not contain model ids, provider names or resource fractions.
    §22.11/§22.12 say those are not part of a personal user's product,
    and filtering at the source is stronger than filtering in the UI --
    what never arrives cannot leak.
    """
    account_type: str = args.account_type
    is_admin = account_type == "administrator"

    target = Path(args.target) if args.target else default_install_location()
    profile = detect_hardware(target)
    calibration = calibrate(profile)
    validation = validate_installation(profile, install_target=target)
    voice = plan_voice(profile, include_cloud_voice=args.cloud_voice and is_admin)

    payload: dict[str, Any] = {
        "account_type": account_type,
        "install_location": str(target),
        "hardware": profile.to_dict(),
        "calibration": calibration.to_dict(account_type=account_type),  # type: ignore[arg-type]
        "voice": voice.to_dict(include_providers=is_admin),
        "validation": validation.to_dict(),
    }

    if calibration.recommended_model is not None:
        payload["recommended_model"] = tier_to_dict(
            calibration.recommended_model, include_model_id=is_admin
        )
    else:
        payload["recommended_model"] = None

    _emit(payload)
    return _EXIT_OK if validation.can_install else _EXIT_BLOCKED


def _validate(args: argparse.Namespace) -> int:
    target = Path(args.target) if args.target else default_install_location()
    report = validate_installation(detect_hardware(target), install_target=target)
    _emit(report.to_dict())
    return _EXIT_OK if report.can_install else _EXIT_BLOCKED


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m jarvis.installer",
        description="JARVIS installer support commands. Every command emits JSON on stdout.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    detect = subparsers.add_parser("detect", help="Scan this machine's hardware.")
    detect.add_argument("--target", help="Planned installation directory.")
    detect.set_defaults(handler=_detect)

    plan = subparsers.add_parser("plan", help="Full installation plan for the summary step.")
    plan.add_argument("--target", help="Planned installation directory.")
    plan.add_argument(
        "--account-type",
        choices=("personal", "administrator"),
        default="personal",
        help="Shapes the payload: a personal plan omits model ids, providers and resource limits.",
    )
    plan.add_argument(
        "--cloud-voice",
        action="store_true",
        help="Include optional cloud speech. Administrator only; ignored otherwise.",
    )
    plan.set_defaults(handler=_plan)

    validate = subparsers.add_parser("validate", help="Pre-installation checks only.")
    validate.add_argument("--target", help="Planned installation directory.")
    validate.set_defaults(handler=_validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handler: Any = args.handler
    return int(handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
