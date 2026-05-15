use serde::Serialize;
use serde_json::Value;
use std::process::Command;
use std::time::Duration;

const DEFAULT_BACKEND_URL: &str = "http://localhost:8010";
const BACKEND_ENV_VARS: [&str; 2] = ["WINTRIP_BACKEND_URL", "OUROBOROS_BACKEND_URL"];

#[derive(Serialize)]
struct BackendConfig {
    backend_url: String,
    approval_phrase: String,
    status: String,
    reachable: bool,
    http_status: Option<u16>,
    health_endpoint: String,
    ouroboros_status_endpoint: String,
    shell_endpoint: String,
    shell_execution: String,
    payload: Option<Value>,
    message: String,
}

fn configured_backend_url() -> String {
    BACKEND_ENV_VARS
        .iter()
        .find_map(|name| {
            std::env::var(name)
                .ok()
                .map(|value| value.trim().trim_end_matches('/').to_owned())
                .filter(|value| !value.is_empty())
        })
        .unwrap_or_else(|| DEFAULT_BACKEND_URL.to_owned())
}

#[tauri::command]
async fn backend_config() -> BackendConfig {
    let backend_url = configured_backend_url();
    let health_endpoint = format!("{backend_url}/status");
    let ouroboros_status_endpoint = format!("{backend_url}/api/ouroboros/status");
    let shell_endpoint = format!("{backend_url}/sandbox/shell");

    let client = match reqwest::Client::builder()
        .timeout(Duration::from_millis(1500))
        .build()
    {
        Ok(client) => client,
        Err(error) => {
            return BackendConfig {
                backend_url,
                approval_phrase: "Akkoord".to_owned(),
                status: "offline".to_owned(),
                reachable: false,
                http_status: None,
                health_endpoint,
                ouroboros_status_endpoint,
                shell_endpoint,
                shell_execution: "python_backend_only".to_owned(),
                payload: None,
                message: format!("Could not create health client: {error}"),
            };
        }
    };

    match client.get(&health_endpoint).send().await {
        Ok(response) => {
            let http_status = response.status().as_u16();
            let reachable = response.status().is_success();
            let payload = response.json::<Value>().await.ok();
            let status = payload
                .as_ref()
                .and_then(|value| value.get("status"))
                .and_then(Value::as_str)
                .unwrap_or(if reachable { "online" } else { "offline" })
                .to_owned();

            BackendConfig {
                backend_url,
                approval_phrase: "Akkoord".to_owned(),
                status,
                reachable,
                http_status: Some(http_status),
                health_endpoint,
                ouroboros_status_endpoint,
                shell_endpoint,
                shell_execution: "python_backend_only".to_owned(),
                payload,
                message: if reachable {
                    "Backend health endpoint responded.".to_owned()
                } else {
                    format!("Backend health endpoint returned HTTP {http_status}.")
                },
            }
        }
        Err(error) => BackendConfig {
            backend_url,
            approval_phrase: "Akkoord".to_owned(),
            status: "offline".to_owned(),
            reachable: false,
            http_status: None,
            health_endpoint,
            ouroboros_status_endpoint,
            shell_endpoint,
            shell_execution: "python_backend_only".to_owned(),
            payload: None,
            message: format!("Backend health endpoint is not reachable: {error}"),
        },
    }
}

#[tauri::command]
fn open_external_url(url: String) -> Result<bool, String> {
    let trimmed = url.trim();
    if trimmed.is_empty() || trimmed.len() > 2048 || trimmed.chars().any(|ch| ch.is_control()) {
        return Err("Invalid external URL.".to_owned());
    }
    if !(trimmed.starts_with("https://") || trimmed.starts_with("http://")) {
        return Err("Only http(s) URLs can be opened externally.".to_owned());
    }

    #[cfg(target_os = "linux")]
    let candidates: [(&str, &[&str]); 3] = [
        ("xdg-open", &[trimmed]),
        ("gio", &["open", trimmed]),
        ("flatpak-spawn", &["--host", "xdg-open", trimmed]),
    ];

    #[cfg(target_os = "macos")]
    let candidates: [(&str, &[&str]); 1] = [("open", &[trimmed])];

    #[cfg(target_os = "windows")]
    let candidates: [(&str, &[&str]); 1] = [("rundll32", &["url.dll,FileProtocolHandler", trimmed])];

    for (program, args) in candidates {
        match Command::new(program).args(args).spawn() {
            Ok(_) => return Ok(true),
            Err(_) => continue,
        }
    }
    Err("No external URL opener was available.".to_owned())
}

#[cfg(target_os = "linux")]
fn allow_linux_user_media_permissions(app: &tauri::App) -> tauri::Result<()> {
    use tauri::Manager;
    use webkit2gtk::{glib::ObjectExt, PermissionRequestExt, WebViewExt};

    if let Some(window) = app.get_webview_window("main") {
        window.with_webview(|webview| {
            webview.inner().connect_permission_request(|_, request| {
                if request.is::<webkit2gtk::UserMediaPermissionRequest>() {
                    request.allow();
                    true
                } else {
                    false
                }
            });
        })?;
    }

    Ok(())
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            #[cfg(target_os = "linux")]
            allow_linux_user_media_permissions(app)?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![backend_config, open_external_url])
        .run(tauri::generate_context!())
        .expect("error while running Ouroboros Cockpit");
}
