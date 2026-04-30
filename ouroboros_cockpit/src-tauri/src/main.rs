use serde::Serialize;
use serde_json::Value;
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

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![backend_config])
        .run(tauri::generate_context!())
        .expect("error while running Ouroboros Cockpit");
}
