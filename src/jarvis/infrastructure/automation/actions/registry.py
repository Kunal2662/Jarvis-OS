"""Maps :class:`ActionType` -> concrete action instance.

Every action class is stateless, so one shared instance per type is safe
and avoids reconstructing objects on every plan step.
"""

from __future__ import annotations

from jarvis.core.exceptions import ActionNotFoundError
from jarvis.domain.automation.models import ActionType
from jarvis.infrastructure.automation.actions.app_actions import (
    CloseAppAction,
    LaunchUrlAction,
    OpenAppAction,
)
from jarvis.infrastructure.automation.actions.base import BaseAction
from jarvis.infrastructure.automation.actions.file_actions import (
    CopyAction,
    CreateFolderAction,
    DeleteFolderAction,
    EmptyRecycleBinAction,
    MoveAction,
    OpenDocumentsAction,
    OpenDownloadsAction,
    OpenExplorerAction,
    RenameAction,
)
from jarvis.infrastructure.automation.actions.search_actions import (
    SearchGoogleAction,
    SearchYoutubeAction,
)
from jarvis.infrastructure.automation.actions.system_actions import (
    ClipboardCopyAction,
    ClipboardPasteAction,
    LockPcAction,
    MuteAction,
    OpenSettingsAction,
    RestartAction,
    ScreenshotAction,
    SetBrightnessAction,
    SetVolumeAction,
    ShutdownAction,
    SleepAction,
    TerminalCommandAction,
)

ACTION_REGISTRY: dict[ActionType, BaseAction] = {
    ActionType.OPEN_APP: OpenAppAction(),
    ActionType.CLOSE_APP: CloseAppAction(),
    ActionType.LAUNCH_URL: LaunchUrlAction(),
    ActionType.SEARCH_GOOGLE: SearchGoogleAction(),
    ActionType.SEARCH_YOUTUBE: SearchYoutubeAction(),
    ActionType.SCREENSHOT: ScreenshotAction(),
    ActionType.CLIPBOARD_COPY: ClipboardCopyAction(),
    ActionType.CLIPBOARD_PASTE: ClipboardPasteAction(),
    ActionType.CREATE_FOLDER: CreateFolderAction(),
    ActionType.DELETE_FOLDER: DeleteFolderAction(),
    ActionType.RENAME: RenameAction(),
    ActionType.MOVE: MoveAction(),
    ActionType.COPY: CopyAction(),
    ActionType.OPEN_EXPLORER: OpenExplorerAction(),
    ActionType.OPEN_DOWNLOADS: OpenDownloadsAction(),
    ActionType.OPEN_DOCUMENTS: OpenDocumentsAction(),
    ActionType.EMPTY_RECYCLE_BIN: EmptyRecycleBinAction(),
    ActionType.SET_VOLUME: SetVolumeAction(),
    ActionType.MUTE: MuteAction(),
    ActionType.SET_BRIGHTNESS: SetBrightnessAction(),
    ActionType.SHUTDOWN: ShutdownAction(),
    ActionType.RESTART: RestartAction(),
    ActionType.SLEEP: SleepAction(),
    ActionType.LOCK_PC: LockPcAction(),
    ActionType.OPEN_SETTINGS: OpenSettingsAction(),
    ActionType.TERMINAL_COMMAND: TerminalCommandAction(),
}


def get_action(action_type: ActionType) -> BaseAction:
    try:
        return ACTION_REGISTRY[action_type]
    except KeyError as err:
        raise ActionNotFoundError(f"No action registered for {action_type!r}.") from err
