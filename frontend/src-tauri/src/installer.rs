//! The Windows host bridge -- M22 Task Group C.
//!
//! Implements the host side of the transport contract the frontend
//! defined in `features/installer/provisioning-transport.ts`. That file
//! is the specification; this file satisfies it. The payload shapes,
//! the command names and the event name all come from there and are
//! **not** redesigned here.
//!
//! # What this bridges
//!
//! The installer UI runs in a webview and cannot spawn a process. The
//! provisioning engine is a Python package invoked as
//! `python -m jarvis.installer provision --stream`, which writes
//! newline-delimited JSON to stdout. This module spawns it, relays each
//! line as a Tauri event, and resolves when the process exits.
//!
//! # Rules it follows
//!
//! **stdout is data, stderr is diagnostics.** Only stdout lines become
//! events. The Python CLI reserves stdout for JSON precisely so a log
//! line cannot be mistaken for a progress event; stderr is captured for
//! logging and, on failure, for the error message -- which is what makes
//! a failure diagnosable instead of "exit code 1".
//!
//! **It never hangs.** Three independent guards: an inactivity timeout,
//! an explicit cancel command, and a kill on drop. A download that
//! stalls forever must not leave the user on a progress bar that never
//! moves.
//!
//! **It never fabricates progress.** If the process cannot start, the
//! command returns an error naming the reason. No synthetic events are
//! emitted under any failure path.

use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{mpsc, Arc, Mutex};
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, Manager, State};

/// The event the frontend listens on. Fixed by
/// `provisioning-transport.ts`; renaming it breaks the contract.
const PROVISION_EVENT: &str = "provisioning://event";

/// A provisioning run with no output for this long is treated as hung.
///
/// Generous, because a checksum pass over a multi-gigabyte model
/// produces no output while it works. Short enough that a genuinely
/// wedged process does not strand the installer forever.
const INACTIVITY_TIMEOUT: Duration = Duration::from_secs(15 * 60);

/// How often the relay loop wakes when the child is quiet.
///
/// Only bounds how quickly cancellation is noticed and how precisely the
/// inactivity timeout fires -- not a poll of the child, which pushes its
/// output. Short enough that Cancel feels immediate, long enough that a
/// silent download costs two wakeups a second.
const OUTPUT_POLL: Duration = Duration::from_millis(500);

/// How long a cancelled process is given to exit on its own before it
/// is killed. The engine's journal means an abrupt kill is recoverable,
/// so this only needs to cover an orderly exit.
const GRACEFUL_SHUTDOWN: Duration = Duration::from_secs(5);

#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ProvisionArgs {
    /// The installation directory the user chose.
    pub location: String,
    /// `personal` or `administrator`. Shapes the payload the Python side
    /// emits -- a personal run carries no model ids or sources.
    pub account_type: String,
}

/// Tracks the running child so `cancel_provisioning` can reach it.
///
/// A `Mutex<Option<Child>>` rather than a channel: cancellation needs to
/// *kill* the process, which requires the handle itself, and only one
/// provisioning run is ever in flight.
#[derive(Default)]
pub struct ProvisioningState {
    child: Mutex<Option<Child>>,
    cancelled: Arc<AtomicBool>,
    /// Where the last run installed to.
    ///
    /// `launch_application` and `open_installation_folder` take **no
    /// arguments** -- that is the documented contract, and the frontend
    /// calls them that way. They still need a path, so the host
    /// remembers the one it was given rather than the contract growing
    /// a parameter to carry information the host already has.
    location: Mutex<Option<String>>,
}

/// Locate the Python interpreter that owns the installer package.
///
/// Ordered by how specific the answer is, because a machine may have
/// several Pythons and only one of them has `jarvis` importable:
///
/// 1. `JARVIS_PYTHON` -- an explicit override, for a packaged runtime or
///    an unusual deployment.
/// 2. The virtual environment beside the application, which is what a
///    packaged installation ships.
/// 3. `python` on `PATH`, for a development checkout.
///
/// Returns `None` when none of them exists, so the caller can report
/// "Python unavailable" rather than failing later with a confusing
/// spawn error.
fn find_python(app: &AppHandle) -> Option<PathBuf> {
    if let Ok(explicit) = std::env::var("JARVIS_PYTHON") {
        let path = PathBuf::from(explicit);
        if path.is_file() {
            log::info!("using JARVIS_PYTHON interpreter at {}", path.display());
            return Some(path);
        }
        log::warn!("JARVIS_PYTHON is set but {} does not exist", path.display());
    }

    // A packaged installation ships its runtime beside the executable.
    if let Ok(resource_dir) = app.path().resource_dir() {
        for relative in [
            Path::new(".venv").join("Scripts").join("python.exe"),
            Path::new("runtime").join("python.exe"),
        ] {
            let candidate = resource_dir.join(&relative);
            if candidate.is_file() {
                log::info!("using bundled interpreter at {}", candidate.display());
                return Some(candidate);
            }
        }
    }

    // Development checkout: the repository's own virtual environment,
    // then whatever is on PATH.
    if let Ok(current) = std::env::current_dir() {
        for ancestor in current.ancestors().take(4) {
            let candidate = ancestor.join(".venv").join("Scripts").join("python.exe");
            if candidate.is_file() {
                log::info!("using project interpreter at {}", candidate.display());
                return Some(candidate);
            }
        }
    }

    for name in ["python.exe", "python3.exe", "python"] {
        if let Ok(path) = which_on_path(name) {
            log::info!("using interpreter from PATH at {}", path.display());
            return Some(path);
        }
    }

    None
}

/// Minimal `which`, rather than a dependency for one function.
fn which_on_path(name: &str) -> Result<PathBuf, ()> {
    let paths = std::env::var_os("PATH").ok_or(())?;
    for directory in std::env::split_paths(&paths) {
        let candidate = directory.join(name);
        if candidate.is_file() {
            return Ok(candidate);
        }
    }
    Err(())
}

/// Build the command, without spawning it.
///
/// Separated so the argument vector is testable and so every caller
/// builds it the same way -- the flags are part of the contract with the
/// Python CLI, not something each command should retype.
fn build_command(python: &Path, subcommand: &str, args: &ProvisionArgs, stream: bool) -> Command {
    let mut command = Command::new(python);
    command
        .arg("-m")
        .arg("jarvis.installer")
        .arg(subcommand)
        .arg("--target")
        .arg(&args.location)
        .arg("--account-type")
        .arg(&args.account_type);

    if stream {
        command.arg("--stream");
    }

    command.stdout(Stdio::piped()).stderr(Stdio::piped());

    // Windows: keep a console window from flashing over the installer.
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }

    command
}

/// The error a command returns to the frontend.
///
/// Plain strings, because `provisioning-types.ts`'s `classifyFailure`
/// reads the message and maps it onto a friendly category. Returning a
/// structured code instead would mean two vocabularies for one failure,
/// and the frontend already owns that mapping.
type BridgeResult<T> = Result<T, String>;

fn python_unavailable() -> String {
    "Python could not be found. JARVIS needs its bundled runtime to install; \
     reinstall the application or set JARVIS_PYTHON to a Python 3.13 interpreter."
        .to_string()
}

/// Run provisioning, relaying the engine's NDJSON stream.
///
/// Resolves when the process exits successfully; rejects with a readable
/// message otherwise. Matches `runProvisioningViaHost`'s expectation
/// that a rejection means "the run did not complete" -- the frontend
/// classifies the message and offers a Retry, which the journal makes a
/// resume rather than a restart.
#[tauri::command]
pub async fn run_provisioning(
    app: AppHandle,
    state: State<'_, ProvisioningState>,
    location: String,
    account_type: String,
) -> BridgeResult<()> {
    let args = ProvisionArgs {
        location,
        account_type,
    };
    log::info!(
        "provisioning starting: target={} account={}",
        args.location,
        args.account_type
    );

    let python = find_python(&app).ok_or_else(python_unavailable)?;
    state.cancelled.store(false, Ordering::SeqCst);
    if let Ok(mut slot) = state.location.lock() {
        *slot = Some(args.location.clone());
    }

    let mut child = build_command(&python, "provision", &args, true)
        .spawn()
        .map_err(|err| format!("Could not start the installer process: {err}"))?;

    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "The installer process produced no output stream.".to_string())?;
    let stderr = child.stderr.take();

    // stderr on its own thread: a full pipe blocks the writer, so a
    // chatty process would deadlock if nobody drained it.
    let stderr_log = Arc::new(Mutex::new(String::new()));
    if let Some(stderr) = stderr {
        let sink = Arc::clone(&stderr_log);
        std::thread::spawn(move || {
            for line in BufReader::new(stderr).lines().map_while(Result::ok) {
                log::warn!("installer stderr: {line}");
                if let Ok(mut buffer) = sink.lock() {
                    buffer.push_str(&line);
                    buffer.push('\n');
                }
            }
        });
    }

    {
        let mut slot = state.child.lock().map_err(|_| "Installer state is poisoned.")?;
        *slot = Some(child);
    }

    let cancelled = Arc::clone(&state.cancelled);
    let mut last_output = Instant::now();
    let mut relayed = 0_usize;

    // stdout is read on its own thread and delivered over a channel
    // rather than iterated directly here.
    //
    // Reading a pipe blocks. Iterating `lines()` on this thread means the
    // inactivity check only runs *after* a line arrives -- so a process
    // that hangs producing no output, which is the one case the timeout
    // exists for, would never reach it. A channel makes waiting
    // interruptible: `recv_timeout` returns whether or not the child has
    // anything to say, which is what makes both the timeout and prompt
    // cancellation real rather than nominal.
    let (tx, rx) = mpsc::channel::<String>();
    std::thread::spawn(move || {
        for line in BufReader::new(stdout).lines().map_while(Result::ok) {
            // A closed receiver means the run is over; stop reading
            // rather than draining into nothing.
            if tx.send(line).is_err() {
                return;
            }
        }
    });

    loop {
        if cancelled.load(Ordering::SeqCst) {
            log::info!("provisioning cancelled after {relayed} events");
            break;
        }

        match rx.recv_timeout(OUTPUT_POLL) {
            Ok(line) => {
                if line.trim().is_empty() {
                    continue;
                }
                last_output = Instant::now();
                relayed += 1;
                // Relayed verbatim. The frontend parses it -- re-encoding
                // here would be a second place the payload shape is
                // known, and the contract says the payload is the
                // engine's.
                if let Err(err) = app.emit(PROVISION_EVENT, line) {
                    log::error!("could not emit provisioning event: {err}");
                }
            }
            // Nothing yet. Normal during a long download; only a
            // problem once it has gone on for INACTIVITY_TIMEOUT.
            Err(mpsc::RecvTimeoutError::Timeout) => {
                if last_output.elapsed() > INACTIVITY_TIMEOUT {
                    log::error!("provisioning produced no output for {INACTIVITY_TIMEOUT:?}");
                    terminate(&state);
                    return Err(
                        "The installation stopped responding. Your progress has been saved, \
                         so continuing will resume from where it stopped."
                            .to_string(),
                    );
                }
            }
            // stdout closed: the process has finished writing.
            Err(mpsc::RecvTimeoutError::Disconnected) => break,
        }
    }

    // Checked before the exit status, because cancelling *removes* the
    // child: `terminate` clears the slot, so asking for the status first
    // would report "the process disappeared" for an ordinary cancel --
    // and `classifyFailure` looks for the word "cancel" to show the
    // cancelled state rather than an error.
    if cancelled.load(Ordering::SeqCst) {
        terminate(&state);
        return Err("Installation cancelled. You can pick up where you left off.".to_string());
    }

    let status = {
        let mut slot = state.child.lock().map_err(|_| "Installer state is poisoned.")?;
        match slot.as_mut() {
            Some(child) => child.wait().map_err(|err| format!("Installer did not exit cleanly: {err}"))?,
            None => return Err("The installer process disappeared.".to_string()),
        }
    };
    {
        let mut slot = state.child.lock().map_err(|_| "Installer state is poisoned.")?;
        *slot = None;
    }

    if status.success() {
        log::info!("provisioning finished, {relayed} events relayed");
        return Ok(());
    }

    // Exit code 2 is the engine's "blocked" code: it ran and reported a
    // real failure, which the stream has already described. Anything
    // else is an unexpected crash, and stderr is the only clue.
    let diagnostics = stderr_log
        .lock()
        .map(|buffer| buffer.trim().to_string())
        .unwrap_or_default();

    let code = status.code().unwrap_or(-1);
    log::error!("provisioning exited with {code}: {diagnostics}");

    if code == 2 {
        Err("The installation could not be completed. Your progress has been saved.".to_string())
    } else if diagnostics.is_empty() {
        Err(format!("The installer stopped unexpectedly (code {code})."))
    } else {
        // The last stderr line is the useful one; the whole traceback
        // would be unreadable in a toast.
        let last = diagnostics.lines().last().unwrap_or(&diagnostics).to_string();
        Err(format!("The installer stopped unexpectedly: {last}"))
    }
}

/// Ask a running installation to stop.
///
/// Additive to the host surface, not a change to the documented
/// transport: the four contract commands are untouched. Cancellation is
/// required by this task group's scope, and it needs a way in.
#[tauri::command]
pub fn cancel_provisioning(state: State<'_, ProvisioningState>) -> BridgeResult<()> {
    log::info!("cancellation requested");
    state.cancelled.store(true, Ordering::SeqCst);
    terminate(&state);
    Ok(())
}

/// Stop the child, gracefully if it will and forcibly if it will not.
fn terminate(state: &State<'_, ProvisioningState>) {
    terminate_child(&state.child);
}

/// The third hang guard: nothing outlives the installer.
///
/// `std::process::Child` *detaches* on drop rather than killing, so
/// without this, closing the installer window mid-run would leave the
/// Python process downloading gigabytes with no window to show for it
/// and no way to stop it. Takes the mutex directly rather than a
/// `State`, since `Drop` has only `&mut self`.
impl Drop for ProvisioningState {
    fn drop(&mut self) {
        terminate_child(&self.child);
    }
}

fn terminate_child(child_slot: &Mutex<Option<Child>>) {
    let Ok(mut slot) = child_slot.lock() else {
        return;
    };
    let Some(child) = slot.as_mut() else {
        return;
    };

    let deadline = Instant::now() + GRACEFUL_SHUTDOWN;
    loop {
        match child.try_wait() {
            Ok(Some(_)) => return,
            Ok(None) if Instant::now() < deadline => {
                std::thread::sleep(Duration::from_millis(100));
            }
            _ => break,
        }
    }

    // An abrupt kill is safe here: the journal records only completed
    // steps, so a step interrupted mid-flight is simply re-run.
    if let Err(err) = child.kill() {
        log::warn!("could not kill installer process: {err}");
    }
    let _ = child.wait();
    *slot = None;
}

/// Fetch the installation plan.
///
/// Non-streaming: `plan` emits a single document, which is what
/// `loadPlanViaHost` expects.
#[tauri::command]
pub async fn load_installation_plan(
    app: AppHandle,
    location: String,
    account_type: String,
) -> BridgeResult<serde_json::Value> {
    let args = ProvisionArgs {
        location,
        account_type,
    };
    log::info!("loading installation plan for {}", args.location);

    let python = find_python(&app).ok_or_else(python_unavailable)?;

    let output = build_command(&python, "plan", &args, false)
        .output()
        .map_err(|err| format!("Could not check this device: {err}"))?;

    // Exit code 2 means the plan was produced *and* found a blocking
    // problem -- the document is valid and the UI renders the failures,
    // so this is not an error at this layer.
    let code = output.status.code().unwrap_or(-1);
    if !output.status.success() && code != 2 {
        let stderr = String::from_utf8_lossy(&output.stderr);
        let last = stderr.trim().lines().last().unwrap_or("no details").to_string();
        log::error!("plan failed with {code}: {stderr}");
        return Err(format!("Could not check this device: {last}"));
    }

    serde_json::from_slice(&output.stdout)
        .map_err(|err| format!("The device check returned something unreadable: {err}"))
}

/// The location the last run installed to.
///
/// An error rather than a guess when nothing has run: opening or
/// launching from a path the host never saw would be inventing one.
fn installed_location(state: &State<'_, ProvisioningState>) -> BridgeResult<String> {
    state
        .location
        .lock()
        .ok()
        .and_then(|slot| slot.clone())
        .ok_or_else(|| "No installation has been completed in this session.".to_string())
}

/// Launch the installed application and close the installer.
#[tauri::command]
pub async fn launch_application(
    app: AppHandle,
    state: State<'_, ProvisioningState>,
) -> BridgeResult<()> {
    let location = installed_location(&state)?;
    let executable = Path::new(&location).join("JARVIS OS.exe");
    log::info!("launching {}", executable.display());

    if !executable.is_file() {
        return Err(format!(
            "JARVIS was not found at {}. Try opening it from the Start Menu.",
            executable.display()
        ));
    }

    let mut command = Command::new(&executable);
    command.current_dir(&location);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const DETACHED_PROCESS: u32 = 0x0000_0008;
        command.creation_flags(DETACHED_PROCESS);
    }

    command
        .spawn()
        .map_err(|err| format!("Could not start JARVIS: {err}"))?;

    // The installer's job is done once the application is up.
    app.exit(0);
    Ok(())
}

/// Reveal the installation folder in Explorer.
#[tauri::command]
pub fn open_installation_folder(state: State<'_, ProvisioningState>) -> BridgeResult<()> {
    let location = installed_location(&state)?;
    log::info!("opening {location}");
    let path = Path::new(&location);
    if !path.is_dir() {
        return Err(format!("{location} no longer exists."));
    }

    #[cfg(windows)]
    {
        Command::new("explorer")
            .arg(path)
            .spawn()
            .map_err(|err| format!("Could not open the folder: {err}"))?;
        return Ok(());
    }

    #[cfg(not(windows))]
    {
        // This task group is Windows-only by scope; other platforms are
        // Task Group D. Saying so beats silently doing nothing.
        Err("Opening the installation folder is only supported on Windows in this build.".to_string())
    }
}
