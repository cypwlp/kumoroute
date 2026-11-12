#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;
mod core;
mod proxy;
mod state;

use std::sync::Mutex;

use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{Manager, RunEvent, WindowEvent};

fn main() {
    let mut store = state::Store::load();
    let profiles = state::Profiles::load(&mut store);
    let app_state = commands::AppState {
        store,
        profiles,
        core: core::Core::new(),
    };

    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.show();
                let _ = w.set_focus();
            }
        }))
        .manage(Mutex::new(app_state))
        .invoke_handler(tauri::generate_handler![
            commands::get_state,
            commands::start_core,
            commands::stop_core,
            commands::set_mode,
            commands::set_system_proxy,
            commands::get_proxy_groups,
            commands::select_proxy,
            commands::test_group_delay,
            commands::add_subscription,
            commands::import_profile,
            commands::update_profile,
            commands::delete_profile,
            commands::set_active_profile,
            commands::get_live,
            commands::get_logs,
            commands::save_stats_export,
            commands::save_settings,
            commands::open_data_dir,
            commands::open_url,
            commands::quit_app,
        ])
        .setup(|app| {
            if let Ok(rd) = app.path().resource_dir() {
                state::set_resource_dir(rd);
            }
            setup_tray(app);
            let shared = app.state::<commands::Shared>();
            let mut s = shared.lock().unwrap();
            let port = s.store.data.controller_port;
            if let Ok(rt) = s.profiles.build_runtime(&s.store) {
                if let Err(e) = s.core.start(port, rt) {
                    state::app_log(&format!("initial core start failed: {e}"));
                }
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            if let RunEvent::ExitRequested { .. } = event {
                let shared = app.state::<commands::Shared>();
                commands::cleanup(&shared);
            }
        });
}

fn setup_tray(app: &tauri::App) {
    let result = (|| -> tauri::Result<()> {
        let show = MenuItem::with_id(app, "show", "顯示主視窗", true, None::<&str>)?;
        let proxy_t = MenuItem::with_id(app, "proxy", "切換系統代理", true, None::<&str>)?;
        let core_t = MenuItem::with_id(app, "core", "啟動/停止核心", true, None::<&str>)?;
        let quit = MenuItem::with_id(app, "quit", "退出 KumoRoute", true, None::<&str>)?;
        let menu = Menu::with_items(app, &[&show, &proxy_t, &core_t, &quit])?;
        let icon = app
            .default_window_icon()
            .cloned()
            .unwrap_or_else(|| tauri::image::Image::new_owned(vec![91, 140, 255, 255], 1, 1));
        TrayIconBuilder::with_id("main")
            .icon(icon)
            .menu(&menu)
            .show_menu_on_left_click(false)
            .on_menu_event(|app, event| {
                let shared = app.state::<commands::Shared>();
                match event.id.as_ref() {
                    "show" => {
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.show();
                            let _ = w.set_focus();
                        }
                    }
                    "proxy" => {
                        let mut s = shared.lock().unwrap();
                        let port = s.store.data.controller_port;
                        let on = proxy::is_on(&s.store);
                        let up = core::is_up(port);
                        let _ = proxy::set_system_proxy(&mut s.store, !on, up);
                    }
                    "core" => {
                        let mut s = shared.lock().unwrap();
                        let port = s.store.data.controller_port;
                        if core::is_up(port) {
                            s.core.stop();
                        } else if let Ok(rt) = s.profiles.build_runtime(&s.store) {
                            let _ = s.core.start(port, rt);
                        }
                    }
                    "quit" => {
                        commands::cleanup(&shared);
                        app.exit(0);
                    }
                    _ => {}
                }
            })
            .on_tray_icon_event(|tray, event| {
                if let TrayIconEvent::Click {
                    button: MouseButton::Left,
                    button_state: MouseButtonState::Up,
                    ..
                } = event
                {
                    let app = tray.app_handle();
                    if let Some(w) = app.get_webview_window("main") {
                        let _ = w.show();
                        let _ = w.set_focus();
                    }
                }
            })
            .build(app)?;
        Ok(())
    })();
    if let Err(e) = result {
        state::app_log(&format!("tray unavailable: {e}"));
    }
}
