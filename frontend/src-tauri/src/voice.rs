use crate::connection::{DesktopConnection, RequestError};
use serde_json::Value;
use std::time::Duration;
use tauri::ipc::{InvokeBody, Request, Response};

const MAX_RECORDING: usize = 1_000_000;
const MAX_SPEECH: usize = 2_000_000;

fn recording(body: &InvokeBody) -> Result<Vec<u8>, RequestError> {
    match body {
        InvokeBody::Raw(bytes) if !bytes.is_empty() && bytes.len() <= MAX_RECORDING => {
            Ok(bytes.clone())
        }
        _ => Err(RequestError::new(
            "Microphone transport requires bounded raw binary audio",
            Some(422),
        )),
    }
}

async fn bounded(mut response: reqwest::Response, limit: usize) -> Result<Vec<u8>, RequestError> {
    let status = response.status().as_u16();
    let mut bytes = Vec::new();
    while let Some(chunk) = response
        .chunk()
        .await
        .map_err(|_| RequestError::new("Voice response interrupted", None))?
    {
        if bytes.len() + chunk.len() > limit {
            return Err(RequestError::new(
                "Voice response exceeds the local size limit",
                Some(502),
            ));
        }
        bytes.extend_from_slice(&chunk);
    }
    if !(200..300).contains(&status) {
        let detail = serde_json::from_slice::<Value>(&bytes)
            .ok()
            .and_then(|json| {
                json.get("detail")
                    .and_then(Value::as_str)
                    .map(|text| text.chars().take(400).collect::<String>())
            })
            .unwrap_or_else(|| "Local voice service unavailable".into());
        return Err(RequestError::new(&detail, Some(status)));
    }
    Ok(bytes)
}

#[tauri::command]
pub async fn orion_transcribe(
    connection: tauri::State<'_, DesktopConnection>,
    request: Request<'_>,
) -> Result<Value, RequestError> {
    let data = recording(request.body())?;
    let response = connection
        .client
        .post("http://127.0.0.1:8000/api/voice/transcribe")
        .timeout(Duration::from_secs(35))
        .header("Content-Type", "audio/wav")
        .body(data)
        .send()
        .await
        .map_err(|_| RequestError::new("Cannot reach the local voice service", None))?;
    let data = bounded(response, 64_000).await?;
    serde_json::from_slice(&data)
        .map_err(|_| RequestError::new("Invalid voice transcription response", Some(502)))
}

#[tauri::command]
pub async fn orion_speak(
    connection: tauri::State<'_, DesktopConnection>,
    text: String,
) -> Result<Response, RequestError> {
    if text.trim().is_empty() || text.chars().count() > 500 {
        return Err(RequestError::new(
            "Speech text must contain 1 to 500 characters",
            Some(422),
        ));
    }
    let response = connection
        .client
        .post("http://127.0.0.1:8000/api/voice/speak")
        .timeout(Duration::from_secs(35))
        .json(&serde_json::json!({"text":text}))
        .send()
        .await
        .map_err(|_| RequestError::new("Cannot reach the local voice service", None))?;
    let data = bounded(response, MAX_SPEECH).await?;
    if data.is_empty() {
        return Err(RequestError::new(
            "Voice service returned empty audio",
            Some(502),
        ));
    }
    Ok(Response::new(data))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn binary_transport_rejects_json_empty_and_oversized_recordings() {
        assert!(recording(&InvokeBody::Raw(vec![1; 44])).is_ok());
        assert!(recording(&InvokeBody::Raw(vec![])).is_err());
        assert!(recording(&InvokeBody::Raw(vec![0; MAX_RECORDING + 1])).is_err());
        assert!(recording(&InvokeBody::Json(serde_json::json!([1, 2, 3]))).is_err());
    }
}
