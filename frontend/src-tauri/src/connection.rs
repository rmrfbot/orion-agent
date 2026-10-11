use reqwest::header::{HeaderMap, HeaderValue};
use serde_json::Value;
use std::time::Duration;

#[derive(serde::Serialize)]
pub struct RequestError {
    message: String,
    status: Option<u16>,
}
impl RequestError {
    fn new(message: &str, status: Option<u16>) -> Self {
        Self {
            message: message.into(),
            status,
        }
    }
}

pub struct DesktopConnection {
    client: reqwest::Client,
}

impl DesktopConnection {
    pub fn new() -> Result<Self, Box<dyn std::error::Error>> {
        let token = include_str!(concat!(env!("OUT_DIR"), "/orion-local-token.txt"));
        let mut value = HeaderValue::from_str(token.trim())?;
        value.set_sensitive(true);
        let mut headers = HeaderMap::new();
        headers.insert("X-ORION-Token", value);
        Ok(Self {
            client: reqwest::Client::builder()
                .default_headers(headers)
                .no_proxy()
                .redirect(reqwest::redirect::Policy::none())
                .timeout(Duration::from_secs(10))
                .build()?,
        })
    }
}

fn allowed_request(method: &str, path: &str) -> bool {
    match (method, path) {
        ("GET", "/health") | ("POST", "/api/tasks") => true,
        ("GET", path) => path.strip_prefix("/api/tasks/").is_some_and(|id| {
            !id.is_empty()
                && id.len() <= 64
                && id.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-')
        }),
        _ => false,
    }
}

#[tauri::command]
pub async fn orion_request(
    connection: tauri::State<'_, DesktopConnection>,
    path: String,
    method: String,
    body: Option<Value>,
) -> Result<Value, RequestError> {
    if !allowed_request(&method, &path) {
        return Err(RequestError::new("Unsupported ORION request", Some(400)));
    }
    let method = reqwest::Method::from_bytes(method.as_bytes())
        .map_err(|_| RequestError::new("Invalid request method", Some(400)))?;
    let mut request = connection
        .client
        .request(method, format!("http://127.0.0.1:8000{path}"));
    if let Some(body) = body {
        request = request.json(&body);
    }
    let response = request
        .send()
        .await
        .map_err(|_| RequestError::new("Cannot connect to the local ORION backend. Start FastAPI; ORION will reconnect automatically.", None))?;
    if !response.status().is_success() {
        let status = response.status().as_u16();
        let message = if status == 401 {
            "ORION authentication failed. Restart tauri dev after changing the backend local token."
        } else {
            "The local ORION backend could not complete this request."
        };
        return Err(RequestError::new(message, Some(status)));
    }
    response
        .json()
        .await
        .map_err(|_| RequestError::new("Local ORION backend returned an invalid response", None))
}

#[cfg(test)]
mod tests {
    use super::allowed_request;

    #[test]
    fn allows_only_local_task_routes() {
        assert!(allowed_request("GET", "/health"));
        assert!(allowed_request("POST", "/api/tasks"));
        assert!(allowed_request("GET", "/api/tasks/abc-123"));
        for path in [
            "https://example.com",
            "//example.com",
            "/api/tasks/../health",
            "/api/tasks/x?redirect=example",
            "/api/tasks/",
            "/docs",
        ] {
            assert!(!allowed_request("GET", path));
        }
        assert!(!allowed_request("DELETE", "/api/tasks/abc-123"));
    }
}
