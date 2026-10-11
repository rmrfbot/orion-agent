// Shared with build.rs so dotenv parsing can be tested without exposing a credential.
pub fn local_token(contents: &str) -> Option<String> {
    let mut token = None;
    for line in contents.lines() {
        let line = line.trim().trim_start_matches('\u{feff}');
        let line = line.strip_prefix("export ").unwrap_or(line).trim();
        let Some((key, raw)) = line.split_once('=') else {
            continue;
        };
        if key.trim() != "ORION_LOCAL_TOKEN" {
            continue;
        }
        let raw = raw.trim();
        let value = if raw.starts_with(['\'', '"']) {
            let quote = raw.chars().next().unwrap();
            let rest = &raw[1..];
            let Some(end) = rest.find(quote) else {
                return None;
            };
            let suffix = rest[end + 1..].trim();
            if !suffix.is_empty() && !suffix.starts_with('#') {
                return None;
            }
            rest[..end].to_owned()
        } else {
            let end = raw
                .char_indices()
                .find_map(|(i, c)| {
                    (c == '#' && i > 0 && raw[..i].ends_with(char::is_whitespace)).then_some(i)
                })
                .unwrap_or(raw.len());
            raw[..end].trim().to_owned()
        };
        token = Some(value);
    }
    token.filter(|value| !value.is_empty() && value.bytes().all(|b| (32..=126).contains(&b)))
}

#[cfg(test)]
mod tests {
    use super::local_token;

    #[test]
    fn reads_only_local_token() {
        assert_eq!(
            local_token("GEMINI_API_KEY=unrelated\nORION_LOCAL_TOKEN=fixture-token\n"),
            Some("fixture-token".into())
        );
    }

    #[test]
    fn handles_dotenv_formatting() {
        for text in [
            "export ORION_LOCAL_TOKEN = 'fixture-token' # comment",
            "\u{feff}ORION_LOCAL_TOKEN=\"fixture-token\"",
            "ORION_LOCAL_TOKEN=fixture-token # comment",
        ] {
            assert_eq!(local_token(text), Some("fixture-token".into()));
        }
        assert_eq!(
            local_token("ORION_LOCAL_TOKEN=first\nORION_LOCAL_TOKEN=last"),
            Some("last".into())
        );
    }

    #[test]
    fn rejects_missing_blank_or_malformed_values() {
        for text in [
            "GEMINI_API_KEY=unrelated",
            "ORION_LOCAL_TOKEN=",
            "ORION_LOCAL_TOKEN='broken",
            "ORION_LOCAL_TOKEN=\"bad\"suffix",
        ] {
            assert!(local_token(text).is_none());
        }
    }
}
