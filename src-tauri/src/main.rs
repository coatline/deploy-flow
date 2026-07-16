#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::{Command, Child};
use std::sync::Mutex;
use tauri::Manager;

struct BackendProcess(Mutex<Option<Child>>);

fn start_backend() -> Option<Child> {
    let backend = Command::new("python")
        .args(["-m", "server.main"])
        .spawn();
    match backend {
        Ok(child) => {
            println!("Backend started with PID: {}", child.id());
            Some(child)
        }
        Err(e) => {
            eprintln!("Failed to start backend: {}", e);
            None
        }
    }
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let child = start_backend();
            app.manage(BackendProcess(Mutex::new(child)));
            Ok(())
        })
        .on_event(|app, event| {
            if let tauri::RunEvent::ExitRequested { .. } = event {
                if let Some(state) = app.try_state::<BackendProcess>() {
                    if let Ok(mut guard) = state.0.lock() {
                        if let Some(ref mut child) = *guard {
                            let _ = child.kill();
                        }
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
