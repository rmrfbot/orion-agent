use std::{str::FromStr, sync::Mutex};
use tauri::{Emitter, LogicalSize, Manager, PhysicalPosition, PhysicalSize, State, WebviewWindow};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, Shortcut};

pub const DEFAULT_SHORTCUT: &str = "Ctrl+Shift+Space";
#[derive(Default)]
pub struct OverlayState(pub Mutex<Overlay>);
pub struct Overlay {
    pub compact: bool,
    expanded: Option<(PhysicalSize<u32>, PhysicalPosition<i32>)>,
    compact_position: Option<PhysicalPosition<i32>>,
    pub shortcut: String,
    pub shortcut_error: Option<String>,
}
impl Default for Overlay {
    fn default() -> Self {
        Self {
            compact: true,
            expanded: None,
            compact_position: None,
            shortcut: DEFAULT_SHORTCUT.into(),
            shortcut_error: None,
        }
    }
}

#[derive(serde::Serialize)]
pub struct WindowInfo {
    compact: bool,
    shortcut: String,
    shortcut_error: Option<String>,
}

fn info(state: &Overlay) -> WindowInfo {
    WindowInfo {
        compact: state.compact,
        shortcut: state.shortcut.clone(),
        shortcut_error: state.shortcut_error.clone(),
    }
}

fn height(requested: f64, available: f64) -> f64 {
    if requested.is_finite() {
        requested.clamp(280.0, available.clamp(280.0, 600.0))
    } else {
        360.0
    }
}

fn clamp_position(
    position: PhysicalPosition<i32>,
    size: PhysicalSize<u32>,
    origin: PhysicalPosition<i32>,
    available: PhysicalSize<u32>,
) -> PhysicalPosition<i32> {
    PhysicalPosition::new(
        position.x.clamp(
            origin.x,
            origin.x + available.width.saturating_sub(size.width) as i32,
        ),
        position.y.clamp(
            origin.y,
            origin.y + available.height.saturating_sub(size.height) as i32,
        ),
    )
}

fn place(
    window: &WebviewWindow,
    size: PhysicalSize<u32>,
    position: PhysicalPosition<i32>,
) -> Result<(), String> {
    if let Some(monitor) = window.current_monitor().ok().flatten() {
        let area = monitor.work_area();
        let size = PhysicalSize::new(
            size.width.min(area.size.width),
            size.height.min(
                area.size
                    .height
                    .saturating_sub((48.0 * monitor.scale_factor()) as u32),
            ),
        );
        window.set_size(size).map_err(|e| e.to_string())?;
        let outer = window.outer_size().map_err(|e| e.to_string())?;
        window
            .set_position(clamp_position(position, outer, area.position, area.size))
            .map_err(|e| e.to_string())?;
    } else {
        window.set_size(size).map_err(|e| e.to_string())?;
        window.center().map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[tauri::command]
pub fn orion_window_info(state: State<OverlayState>) -> Result<WindowInfo, String> {
    let locked = state.0.lock().map_err(|_| "Window state unavailable")?;
    Ok(info(&locked))
}

#[tauri::command]
pub fn orion_window_mode(
    window: WebviewWindow,
    state: State<OverlayState>,
    compact: bool,
) -> Result<WindowInfo, String> {
    let mut state = state.0.lock().map_err(|_| "Window state unavailable")?;
    if state.compact != compact {
        if compact {
            state.expanded = Some((
                window.inner_size().map_err(|e| e.to_string())?,
                window.outer_position().map_err(|e| e.to_string())?,
            ));
            window.set_decorations(false).map_err(|e| e.to_string())?;
            window
                .set_min_size(Some(LogicalSize::new(360.0, 280.0)))
                .map_err(|e| e.to_string())?;
            window
                .set_size(LogicalSize::new(420.0, 360.0))
                .map_err(|e| e.to_string())?;
            if let Some(position) = state.compact_position {
                place(
                    &window,
                    window.inner_size().map_err(|e| e.to_string())?,
                    position,
                )?;
            } else {
                window.center().map_err(|e| e.to_string())?;
            }
        } else {
            state.compact_position = Some(window.outer_position().map_err(|e| e.to_string())?);
            window.set_decorations(true).map_err(|e| e.to_string())?;
            window
                .set_min_size(Some(LogicalSize::new(900.0, 560.0)))
                .map_err(|e| e.to_string())?;
            if let Some((size, position)) = state.expanded {
                place(&window, size, position)?;
            } else {
                window
                    .set_size(LogicalSize::new(1200.0, 680.0))
                    .map_err(|e| e.to_string())?;
                place(
                    &window,
                    window.inner_size().map_err(|e| e.to_string())?,
                    window.outer_position().map_err(|e| e.to_string())?,
                )?;
                window.center().map_err(|e| e.to_string())?;
            }
        }
        window
            .set_always_on_top(compact)
            .map_err(|e| e.to_string())?;
        state.compact = compact;
    }
    window.show().map_err(|e| e.to_string())?;
    window.unminimize().map_err(|e| e.to_string())?;
    window.set_focus().map_err(|e| e.to_string())?;
    Ok(info(&state))
}

#[tauri::command]
pub fn orion_compact_height(
    window: WebviewWindow,
    state: State<OverlayState>,
    requested: f64,
) -> Result<(), String> {
    if state
        .0
        .lock()
        .map_err(|_| "Window state unavailable")?
        .compact
    {
        let available = window
            .current_monitor()
            .ok()
            .flatten()
            .map(|m| m.work_area().size.height as f64 / m.scale_factor() - 40.0)
            .unwrap_or(600.0);
        window
            .set_size(LogicalSize::new(420.0, height(requested, available)))
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[tauri::command]
pub fn orion_window_action(window: WebviewWindow, action: String) -> Result<(), String> {
    match action.as_str() {
        "drag" => window.start_dragging(),
        "minimize" => {
            let _ = window.emit("orion-inactive", ());
            window.minimize()
        }
        "show" => window
            .show()
            .and_then(|_| window.unminimize())
            .and_then(|_| window.set_focus()),
        _ => return Err("Unsupported window action".into()),
    }
    .map_err(|e| e.to_string())
}

#[tauri::command]
pub fn orion_shortcut(
    app: tauri::AppHandle,
    state: State<OverlayState>,
    shortcut: String,
) -> Result<WindowInfo, String> {
    let parsed =
        Shortcut::from_str(&shortcut).map_err(|_| "Use a shortcut such as Ctrl+Shift+Space")?;
    if !parsed
        .mods
        .contains(tauri_plugin_global_shortcut::Modifiers::CONTROL)
        || !parsed
            .mods
            .contains(tauri_plugin_global_shortcut::Modifiers::SHIFT)
    {
        return Err(
            "Shortcut must include Ctrl and Shift to avoid intercepting ordinary typing".into(),
        );
    }
    let mut state = state.0.lock().map_err(|_| "Window state unavailable")?;
    if state.shortcut == shortcut && state.shortcut_error.is_none() {
        return Ok(info(&state));
    }
    app.global_shortcut().register(parsed).map_err(
        |_| "Shortcut is unavailable or already in use; the previous shortcut remains active",
    )?;
    if state.shortcut_error.is_none() {
        if app
            .global_shortcut()
            .unregister(state.shortcut.as_str())
            .is_err()
        {
            let _ = app.global_shortcut().unregister(parsed);
            return Err("Could not replace the previous shortcut".into());
        }
    }
    state.shortcut = shortcut;
    state.shortcut_error = None;
    Ok(info(&state))
}

pub fn initialize(app: &tauri::AppHandle) {
    let result = app.global_shortcut().register(DEFAULT_SHORTCUT);
    if result.is_err() {
        if let Ok(mut state) = app.state::<OverlayState>().0.lock() {
            state.shortcut_error = Some(
                "Ctrl+Shift+Space is unavailable. Choose another shortcut in Mission Control."
                    .into(),
            );
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn compact_height_is_bounded_and_handles_invalid_input() {
        assert_eq!(height(100.0, 768.0), 280.0);
        assert_eq!(height(900.0, 500.0), 500.0);
        assert_eq!(height(f64::NAN, 768.0), 360.0);
    }
    #[test]
    fn initial_mode_and_shortcut_are_consistent() {
        let state = Overlay::default();
        assert!(state.compact);
        assert!(Shortcut::from_str(&state.shortcut).is_ok());
        assert!(state.expanded.is_none());
    }
    #[test]
    fn restored_positions_stay_inside_the_current_work_area() {
        let result = clamp_position(
            PhysicalPosition::new(-2000, 2000),
            PhysicalSize::new(420, 360),
            PhysicalPosition::new(0, 0),
            PhysicalSize::new(1366, 728),
        );
        assert_eq!(result, PhysicalPosition::new(0, 368));
    }
}
