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
from jarvis.installer.dependencies import detect_dependencies
from jarvis.installer.hardware import detect_hardware
from jarvis.installer.journal import ProvisioningJournal
from jarvis.installer.local_model import tier_to_dict
from jarvis.installer.manifest import read_manifest
from jarvis.installer.provisioning import ProvisioningEngine, repair_step_from_key
from jarvis.installer.sources import registry_from_environment
from jarvis.installer.validation import default_install_location, validate_installation
from jarvis.installer.verification import verify_installation
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


def _dependencies(args: argparse.Namespace) -> int:
    """Detect runtime dependencies. Never installs anything."""
    report = detect_dependencies()
    _emit(report.to_dict(include_paths=args.account_type == "administrator"))
    return _EXIT_OK if report.satisfied else _EXIT_BLOCKED


def _provision(args: argparse.Namespace) -> int:
    """Run (or resume) provisioning.

    There is no separate `resume` command: `provision` skips whatever the
    journal records as complete, so resuming *is* running it again. A
    resume that took a different code path would be the path least often
    exercised and most often broken.
    """
    is_admin = args.account_type == "administrator"
    target = Path(args.target) if args.target else default_install_location()

    profile = detect_hardware(target)
    calibration = calibrate(profile)
    voice = plan_voice(profile, include_cloud_voice=args.cloud_voice and is_admin)

    engine = ProvisioningEngine(
        target,
        registry=registry_from_environment(),
        hardware=profile,
        calibration=calibration,
        voice_plan=voice,
        account_type=args.account_type,
        online=profile.internet is not False,
    )

    if args.stream:
        # NDJSON: one `{"event": "progress", ...}` line per callback,
        # then a final `{"event": "result", ...}`. A stream rather than
        # one document at the end because a UI cannot show live progress
        # for a multi-gigabyte download from a value it receives once the
        # download is over.
        #
        # `flush=True` on every line: without it the pipe buffers, and a
        # progress stream that arrives all at once at the end is exactly
        # the thing it exists not to be.
        def _emit_line(payload: dict[str, Any]) -> None:
            json.dump(payload, sys.stdout, default=str)
            sys.stdout.write("\n")
            sys.stdout.flush()

        def _stream(progress: Any) -> None:
            _emit_line({"event": "progress", **progress.to_dict(include_detail=is_admin)})

        result = engine.provision(on_progress=_stream)
        _emit_line({"event": "result", **result.to_dict(include_detail=is_admin)})
        return _EXIT_OK if result.succeeded else _EXIT_BLOCKED

    result = engine.provision()
    _emit(result.to_dict(include_detail=is_admin))
    return _EXIT_OK if result.succeeded else _EXIT_BLOCKED


def _verify(args: argparse.Namespace) -> int:
    target = Path(args.target) if args.target else default_install_location()
    report = verify_installation(target, manifest=read_manifest(target))
    _emit(report.to_dict())
    return _EXIT_OK if report.healthy else _EXIT_BLOCKED


def _repair(args: argparse.Namespace) -> int:
    """Redo one step and everything after it."""
    step = repair_step_from_key(args.step)
    if step is None:
        _emit({"error": f"Unknown repair target {args.step!r}."})
        return _EXIT_BLOCKED

    is_admin = args.account_type == "administrator"
    target = Path(args.target) if args.target else default_install_location()
    profile = detect_hardware(target)

    engine = ProvisioningEngine(
        target,
        registry=registry_from_environment(),
        hardware=profile,
        calibration=calibrate(profile),
        voice_plan=plan_voice(profile),
        account_type=args.account_type,
        online=profile.internet is not False,
    )
    result = engine.repair(step)
    _emit(result.to_dict(include_detail=is_admin))
    return _EXIT_OK if result.succeeded else _EXIT_BLOCKED


def _status(args: argparse.Namespace) -> int:
    """What an interrupted installation got through."""
    target = Path(args.target) if args.target else default_install_location()
    journal = ProvisioningJournal(target / "config")
    _emit(
        {
            "install_location": str(target),
            "journal": journal.to_dict(),
            "manifest": read_manifest(target) is not None,
        }
    )
    return _EXIT_OK


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

    # --- M22 Task Group B ---------------------------------------------

    def _with_account(sub: argparse.ArgumentParser) -> argparse.ArgumentParser:
        sub.add_argument("--target", help="Installation directory.")
        sub.add_argument(
            "--account-type",
            choices=("personal", "administrator"),
            default="personal",
            help="Shapes the payload: a personal one omits ids, sources and paths.",
        )
        return sub

    dependencies = _with_account(
        subparsers.add_parser("dependencies", help="Detect runtime dependencies. Installs nothing.")
    )
    dependencies.set_defaults(handler=_dependencies)

    provision = _with_account(
        subparsers.add_parser("provision", help="Run or resume provisioning.")
    )
    provision.add_argument(
        "--cloud-voice", action="store_true", help="Administrator only; ignored otherwise."
    )
    provision.add_argument(
        "--stream",
        action="store_true",
        help=(
            "Emit newline-delimited progress events, then a final result. "
            "Without it the output is a single document, unchanged."
        ),
    )
    provision.set_defaults(handler=_provision)

    verify = _with_account(subparsers.add_parser("verify", help="Verify an installation."))
    verify.set_defaults(handler=_verify)

    repair = _with_account(
        subparsers.add_parser("repair", help="Redo a step and everything after it.")
    )
    repair.add_argument(
        "step",
        help="dependencies | directories | configuration | model_download | "
        "voice_download | first_run | verification | manifest",
    )
    repair.set_defaults(handler=_repair)

    status = subparsers.add_parser("status", help="What provisioning has completed so far.")
    status.add_argument("--target", help="Installation directory.")
    status.set_defaults(handler=_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handler: Any = args.handler
    return int(handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
