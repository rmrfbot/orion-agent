#[cfg(test)]
mod build_config;
mod connection;
mod overlay;
mod voice;
use tauri::{Emitter, Manager};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(overlay::OverlayState::default())
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, _, event| {
                    if event.state() == ShortcutState::Pressed {
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.unminimize();
                            let _ = window.set_focus();
                            let _ = window.emit("orion-summoned", ());
                        }
                    }
                })
                .build(),
        )
        .invoke_handler(tauri::generate_handler![
            connection::orion_request,
            voice::orion_transcribe,
            voice::orion_speak,
            overlay::orion_window_info,
            overlay::orion_window_mode,
            overlay::orion_compact_height,
            overlay::orion_window_action,
            overlay::orion_shortcut
        ])
        .setup(|app| {
            app.manage(connection::DesktopConnection::new()?);
            overlay::initialize(app.handle());
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(event, tauri::WindowEvent::CloseRequested { .. })
                || matches!(event, tauri::WindowEvent::Resized(_))
                    && window.is_minimized().unwrap_or(false)
            {
                let _ = window.emit("orion-inactive", ());
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building ORION")
        .run(|app, event| {
            if matches!(event, tauri::RunEvent::Exit) {
                let _ = app.global_shortcut().unregister_all();
            }
        });
}
