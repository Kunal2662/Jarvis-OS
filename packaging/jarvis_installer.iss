; JARVIS OS -- Inno Setup installer script (RC1, section 2)
;
; STATUS: written and reasoned through, NOT yet compiled or tested --
; this environment has no Windows machine and no Inno Setup Compiler
; (ISCC.exe) available to actually build and test the resulting
; installer .exe. Treat as a documented, reviewable starting point.
; See docs/PACKAGING.md for the full honest status.
;
; Prerequisite: packaging/build_windows.ps1 has already been run and
; produced dist/JarvisOS/JarvisOS.exe (see that script / jarvis.spec).
;
; Build this installer (on Windows, with Inno Setup installed):
;   iscc packaging/jarvis_installer.iss

#define MyAppName "JARVIS OS"
#define MyAppVersion "0.3.0"
#define MyAppPublisher "JARVIS OS"
#define MyAppURL "https://github.com/your-org/jarvis-os"
#define MyAppExeName "JarvisOS.exe"

[Setup]
AppId={{8F3A1C4E-9B2D-4E7A-A1F6-2C5D8E9B4A7F}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
; Per-user install by default -- no admin prompt needed, and avoids
; needing elevated permissions just to run a personal AI assistant.
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; PrivilegesRequired=lowest keeps this a no-admin-needed install;
; switch to "admin" only if a future need (e.g. a system service)
; requires it.
PrivilegesRequired=lowest
OutputDir=..\dist\installer
OutputBaseFilename=JarvisOS-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; TODO (Milestone 5.5 RC1, section 1): no .ico asset exists yet
; (resources/icons/ is empty) -- same gap as packaging/jarvis.spec.
; SetupIconFile=..\resources\icons\jarvis.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
; Upgrade support: installing a newer version over an older one just
; works via AppId matching -- Inno Setup handles this automatically,
; no extra config needed for the common case.

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"
; Silent installation: /VERYSILENT /SUPPRESSMSGBOXES on the installer
; command line skips all UI, including these optional tasks (they
; default to unchecked when silent unless explicitly passed via
; /TASKS=desktopicon).

[Files]
; The entire PyInstaller onedir output -- .exe plus all bundled
; Python/Qt/dependency binaries and data files.
Source: "..\dist\JarvisOS\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Offer to launch immediately after a normal (non-silent) install.
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Explicitly does NOT delete the user's data directory
; (%LOCALAPPDATA%\JarvisOS or wherever Settings.resolved_data_dir
; points) on uninstall -- conversations, memories, and settings should
; survive an uninstall/reinstall cycle unless the user explicitly asks
; to wipe them. Only the installed program files are removed, which
; [Files]/DestDir={app} already handles via Inno Setup's own uninstall
; log without needing an entry here.

; Repair installation: Inno Setup's generated uninstaller supports
; "Modify/Repair" out of the box once [Setup] and [Files] are correct
; (re-running the installer over an existing install re-copies
; [Files]) -- no extra scripting needed for the common case.
