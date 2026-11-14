const COMMANDS: &[&str] = &[
    "get_state",
    "start_core",
    "stop_core",
    "set_mode",
    "set_system_proxy",
    "get_proxy_groups",
    "select_proxy",
    "test_group_delay",
    "add_subscription",
    "import_profile",
    "update_profile",
    "delete_profile",
    "set_active_profile",
    "get_live",
    "get_logs",
    "save_stats_export",
    "check_update",
    "install_update",
    "run_update_installer",
    "vpn_list",
    "vpn_connect",
    "vpn_connect_with_credentials",
    "vpn_disconnect",
    "vpn_set_advanced",
    "vpn_open_settings",
    "record_ui_error",
    "diagnostics_preview",
    "export_diagnostics",
    "save_settings",
    "open_data_dir",
    "open_url",
    "quit_app",
];

fn main() {
    tauri_build::try_build(
        tauri_build::Attributes::new()
            .app_manifest(tauri_build::AppManifest::new().commands(COMMANDS)),
    )
    .expect("failed to build Tauri permission manifest");
}