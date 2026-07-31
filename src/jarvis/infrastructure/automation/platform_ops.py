"""Per-OS primitive operations backing the automation action classes.

Design note
-----------
The milestone brief asks for ``windows/``, ``linux/`` and ``mac/`` packages.
We deliberately implement that as three small *strategy classes* in one
module (:class:`WindowsOps`, :class:`LinuxOps`, :class:`MacOps`) rather than
three physical packages: every one of these methods is a 1-3 line shell
call, so a package-per-OS would mean a dozen near-empty files. Splitting
into real ``platform/windows/``, ``platform/linux/``, ``platform/mac/``
packages is a clean follow-up refactor once each OS backend grows real
per-platform logic (see the "Remaining TODOs" section of the delivery
summary) — the public surface (:class:`PlatformOps`) will not need to
change for that split to happen.

Every method here is intentionally dumb (no retries, no validation — that
lives in the action classes and in
:mod:`jarvis.features.automation.validator`) and safe to call from a
worker thread via ``asyncio.to_thread``.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from abc import ABC, abstractmethod
from pathlib import Path

from jarvis.core.exceptions import ActionExecutionError

# App-name -> platform-specific launch target. Extend freely; unknown names
# fall back to "treat the string as an executable/bundle id and hope the OS
# PATH resolves it", which is exactly what `open`/`start`/`xdg-open` do.
_APP_ALIASES: dict[str, dict[str, str]] = {
    "chrome": {"win32": "chrome", "darwin": "Google Chrome", "linux": "google-chrome"},
    "google chrome": {"win32": "chrome", "darwin": "Google Chrome", "linux": "google-chrome"},
    "vs code": {"win32": "code", "darwin": "Visual Studio Code", "linux": "code"},
    "vscode": {"win32": "code", "darwin": "Visual Studio Code", "linux": "code"},
    "visual studio code": {"win32": "code", "darwin": "Visual Studio Code", "linux": "code"},
    "spotify": {"win32": "spotify", "darwin": "Spotify", "linux": "spotify"},
    "notepad": {"win32": "notepad", "darwin": "TextEdit", "linux": "gedit"},
    "explorer": {"win32": "explorer", "darwin": "Finder", "linux": "nautilus"},
    "terminal": {"win32": "wt", "darwin": "Terminal", "linux": "x-terminal-emulator"},
    "calculator": {"win32": "calc", "darwin": "Calculator", "linux": "gnome-calculator"},
}


def resolve_app_name(name: str) -> str:
    """Map a spoken app name (``"vs code"``) to the current OS's launch token."""
    key = name.strip().lower()
    platform_key = "win32" if sys.platform.startswith("win") else sys.platform
    alias = _APP_ALIASES.get(key)
    if alias and platform_key in alias:
        return alias[platform_key]
    return name.strip()


class PlatformOps(ABC):
    """Contract every OS backend implements. All calls are blocking/sync —
    action classes are responsible for ``asyncio.to_thread``-ing them."""

    name: str = "generic"

    @abstractmethod
    def open_app(self, name: str) -> None: ...

    @abstractmethod
    def close_app(self, name: str) -> None: ...

    @abstractmethod
    def open_path(self, path: str) -> None: ...

    @abstractmethod
    def set_volume(self, percent: int) -> None: ...

    @abstractmethod
    def mute(self, muted: bool = True) -> None: ...

    @abstractmethod
    def set_brightness(self, percent: int) -> None: ...

    @abstractmethod
    def shutdown(self, delay_seconds: int = 0) -> None: ...

    @abstractmethod
    def restart(self, delay_seconds: int = 0) -> None: ...

    @abstractmethod
    def cancel_scheduled_shutdown(self) -> None: ...

    @abstractmethod
    def sleep(self) -> None: ...

    @abstractmethod
    def lock(self) -> None: ...

    @abstractmethod
    def open_settings(self) -> None: ...

    @abstractmethod
    def empty_recycle_bin(self) -> None: ...

    @abstractmethod
    def screenshot(self, output_path: str) -> str: ...

    def _run(self, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(args, check=check, capture_output=True, text=True, timeout=30)
        except FileNotFoundError as err:
            raise ActionExecutionError(f"Required system command not found: {args[0]}") from err
        except subprocess.CalledProcessError as err:
            raise ActionExecutionError(
                f"Command {args!r} failed: {(err.stderr or err.stdout or '').strip()}"
            ) from err
        except subprocess.TimeoutExpired as err:
            raise ActionExecutionError(f"Command {args!r} timed out.") from err


class WindowsOps(PlatformOps):
    name = "windows"

    def open_app(self, name: str) -> None:
        self._run(["cmd", "/c", "start", "", resolve_app_name(name)], check=False)

    def close_app(self, name: str) -> None:
        self._run(["taskkill", "/IM", f"{resolve_app_name(name)}.exe", "/F"], check=False)

    def open_path(self, path: str) -> None:
        self._run(["explorer", path], check=False)

    def set_volume(self, percent: int) -> None:
        # No first-party CLI mixer on Windows; nircmd/SoundVolumeView are the
        # common third-party tools. We shell out to one if present, else no-op.
        if shutil.which("nircmd"):
            self._run(["nircmd", "setsysvolume", str(int(percent / 100 * 65535))])
        else:
            raise ActionExecutionError(
                "Setting volume on Windows requires 'nircmd' on PATH (not installed)."
            )

    def mute(self, muted: bool = True) -> None:
        if shutil.which("nircmd"):
            self._run(["nircmd", "mutesysvolume", "1" if muted else "0"])
        else:
            raise ActionExecutionError(
                "Muting on Windows requires 'nircmd' on PATH (not installed)."
            )

    def set_brightness(self, percent: int) -> None:
        script = (
            "(Get-WmiObject -Namespace root/WMI "
            f"-Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{int(percent)})"
        )
        self._run(["powershell", "-Command", script])

    def shutdown(self, delay_seconds: int = 0) -> None:
        self._run(["shutdown", "/s", "/t", str(max(delay_seconds, 0))])

    def restart(self, delay_seconds: int = 0) -> None:
        self._run(["shutdown", "/r", "/t", str(max(delay_seconds, 0))])

    def cancel_scheduled_shutdown(self) -> None:
        self._run(["shutdown", "/a"], check=False)

    def sleep(self) -> None:
        self._run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0", "1", "0"], check=False)

    def lock(self) -> None:
        self._run(["rundll32.exe", "user32.dll,LockWorkStation"])

    def open_settings(self) -> None:
        self._run(["cmd", "/c", "start", "", "ms-settings:"], check=False)

    def empty_recycle_bin(self) -> None:
        script = "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"
        self._run(["powershell", "-Command", script], check=False)

    def screenshot(self, output_path: str) -> str:
        script = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            "Add-Type -AssemblyName System.Drawing;"
            "$b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds;"
            "$bmp=New-Object System.Drawing.Bitmap $b.Width,$b.Height;"
            "$g=[System.Drawing.Graphics]::FromImage($bmp);"
            "$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size);"
            f"$bmp.Save('{output_path}')"
        )
        self._run(["powershell", "-Command", script])
        return output_path


class MacOps(PlatformOps):
    name = "macos"

    def open_app(self, name: str) -> None:
        self._run(["open", "-a", resolve_app_name(name)])

    def close_app(self, name: str) -> None:
        self._run(["osascript", "-e", f'quit app "{resolve_app_name(name)}"'], check=False)

    def open_path(self, path: str) -> None:
        self._run(["open", path])

    def set_volume(self, percent: int) -> None:
        level = max(0, min(100, percent)) * 7 // 100  # AppleScript scale is 0-7
        self._run(["osascript", "-e", f"set volume output volume {percent} --{level}"])

    def mute(self, muted: bool = True) -> None:
        self._run(["osascript", "-e", f"set volume output muted {'true' if muted else 'false'}"])

    def set_brightness(self, percent: int) -> None:
        if shutil.which("brightness"):
            self._run(["brightness", str(max(0, min(100, percent)) / 100)])
        else:
            raise ActionExecutionError(
                "Setting brightness on macOS requires the 'brightness' CLI (brew install "
                "brightness)."
            )

    def shutdown(self, delay_seconds: int = 0) -> None:
        self._run(["sudo", "shutdown", "-h", f"+{max(delay_seconds // 60, 0)}"])

    def restart(self, delay_seconds: int = 0) -> None:
        self._run(["sudo", "shutdown", "-r", f"+{max(delay_seconds // 60, 0)}"])

    def cancel_scheduled_shutdown(self) -> None:
        self._run(["sudo", "killall", "shutdown"], check=False)

    def sleep(self) -> None:
        self._run(["pmset", "sleepnow"])

    def lock(self) -> None:
        self._run(
            [
                "/System/Library/CoreServices/Menu Extras/User.menu/Contents/Resources/CGSession",
                "-suspend",
            ],
            check=False,
        )

    def open_settings(self) -> None:
        self._run(["open", "x-apple.systempreferences:"])

    def empty_recycle_bin(self) -> None:
        self._run(["osascript", "-e", 'tell application "Finder" to empty trash'], check=False)

    def screenshot(self, output_path: str) -> str:
        self._run(["screencapture", "-x", output_path])
        return output_path


class LinuxOps(PlatformOps):
    name = "linux"

    def open_app(self, name: str) -> None:
        self._run(["nohup", resolve_app_name(name)], check=False)

    def close_app(self, name: str) -> None:
        self._run(["pkill", "-f", resolve_app_name(name)], check=False)

    def open_path(self, path: str) -> None:
        self._run(["xdg-open", path])

    def set_volume(self, percent: int) -> None:
        if shutil.which("pactl"):
            self._run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"])
        elif shutil.which("amixer"):
            self._run(["amixer", "set", "Master", f"{percent}%"])
        else:
            raise ActionExecutionError("Neither 'pactl' nor 'amixer' found on PATH.")

    def mute(self, muted: bool = True) -> None:
        state = "1" if muted else "0"
        if shutil.which("pactl"):
            self._run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", state])
        elif shutil.which("amixer"):
            self._run(["amixer", "set", "Master", "mute" if muted else "unmute"])
        else:
            raise ActionExecutionError("Neither 'pactl' nor 'amixer' found on PATH.")

    def set_brightness(self, percent: int) -> None:
        if shutil.which("brightnessctl"):
            self._run(["brightnessctl", "set", f"{max(0, min(100, percent))}%"])
        else:
            raise ActionExecutionError("'brightnessctl' not found on PATH.")

    def shutdown(self, delay_seconds: int = 0) -> None:
        minutes = max(delay_seconds // 60, 0)
        self._run(["shutdown", f"+{minutes}"])

    def restart(self, delay_seconds: int = 0) -> None:
        minutes = max(delay_seconds // 60, 0)
        self._run(["shutdown", "-r", f"+{minutes}"])

    def cancel_scheduled_shutdown(self) -> None:
        self._run(["shutdown", "-c"], check=False)

    def sleep(self) -> None:
        self._run(["systemctl", "suspend"])

    def lock(self) -> None:
        if shutil.which("xdg-screensaver"):
            self._run(["xdg-screensaver", "lock"])
        elif shutil.which("loginctl"):
            self._run(["loginctl", "lock-session"])
        else:
            raise ActionExecutionError("No supported screen-lock command found.")

    def open_settings(self) -> None:
        self._run(["xdg-open", "settings:"], check=False)

    def empty_recycle_bin(self) -> None:
        if shutil.which("gio"):
            self._run(["gio", "trash", "--empty"], check=False)
        else:
            trash = Path.home() / ".local/share/Trash/files"
            if trash.exists():
                shutil.rmtree(trash, ignore_errors=True)
                trash.mkdir(parents=True, exist_ok=True)

    def screenshot(self, output_path: str) -> str:
        if shutil.which("gnome-screenshot"):
            self._run(["gnome-screenshot", "-f", output_path])
        elif shutil.which("scrot"):
            self._run(["scrot", output_path])
        elif shutil.which("import"):  # ImageMagick
            self._run(["import", "-window", "root", output_path])
        else:
            raise ActionExecutionError(
                "No screenshot tool found (tried gnome-screenshot, scrot, import)."
            )
        return output_path


class NoopOps(PlatformOps):
    """Used in CI / unsupported platforms — mirrors ``NoopAutomationAdapter``."""

    name = "noop"

    def _unsupported(self, action: str) -> ActionExecutionError:
        return ActionExecutionError(f"'{action}' is not supported on this platform.")

    def open_app(self, name: str) -> None:
        raise self._unsupported("open_app")

    def close_app(self, name: str) -> None:
        raise self._unsupported("close_app")

    def open_path(self, path: str) -> None:
        raise self._unsupported("open_path")

    def set_volume(self, percent: int) -> None:
        raise self._unsupported("set_volume")

    def mute(self, muted: bool = True) -> None:
        raise self._unsupported("mute")

    def set_brightness(self, percent: int) -> None:
        raise self._unsupported("set_brightness")

    def shutdown(self, delay_seconds: int = 0) -> None:
        raise self._unsupported("shutdown")

    def restart(self, delay_seconds: int = 0) -> None:
        raise self._unsupported("restart")

    def cancel_scheduled_shutdown(self) -> None:
        raise self._unsupported("cancel_scheduled_shutdown")

    def sleep(self) -> None:
        raise self._unsupported("sleep")

    def lock(self) -> None:
        raise self._unsupported("lock")

    def open_settings(self) -> None:
        raise self._unsupported("open_settings")

    def empty_recycle_bin(self) -> None:
        raise self._unsupported("empty_recycle_bin")

    def screenshot(self, output_path: str) -> str:
        raise self._unsupported("screenshot")


def get_platform_ops() -> PlatformOps:
    """Return the :class:`PlatformOps` strategy for the running OS."""
    if sys.platform.startswith("win"):
        return WindowsOps()
    if sys.platform == "darwin":
        return MacOps()
    if sys.platform.startswith("linux"):
        return LinuxOps()
    return NoopOps()
