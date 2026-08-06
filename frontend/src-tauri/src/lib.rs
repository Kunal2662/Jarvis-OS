mod installer;

use installer::ProvisioningState;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        // Backs services/window/window-service.ts's `restoreStateCurrent`/
        // `saveWindowState` calls (Task 14) -- registered here so window
        // size/position/maximized state survives a restart without this app
        // reimplementing that persistence itself.
        .plugin(tauri_plugin_window_state::Builder::default().build())
        // The installer's host bridge (M22 Task Group C). One instance
        // for the process: only one provisioning run is ever in flight,
        // and `cancel_provisioning` needs to reach the child that
        // `run_provisioning` spawned.
        .manage(ProvisioningState::default())
        .invoke_handler(tauri::generate_handler![
            installer::run_provisioning,
            installer::cancel_provisioning,
            installer::load_installation_plan,
            installer::launch_application,
            installer::open_installation_folder,
        ])
        .setup(|app| {
            // Logging is registered unconditionally, not only in debug.
            // An installer that fails on a user's machine is the case
            // where a log is worth most, and that machine is running a
            // release build. Debug additionally logs to stdout.
            let logger = tauri_plugin_log::Builder::default()
                .level(if cfg!(debug_assertions) {
                    log::LevelFilter::Debug
                } else {
                    log::LevelFilter::Info
                })
                .targets([
                    tauri_plugin_log::Target::new(tauri_plugin_log::TargetKind::LogDir {
                        file_name: Some("jarvis-installer".into()),
                    }),
                    tauri_plugin_log::Target::new(tauri_plugin_log::TargetKind::Stdout),
                ]);

            app.handle().plugin(logger.build())?;
            log::info!("JARVIS OS starting, version {}", env!("CARGO_PKG_VERSION"));
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
