//! Shared job options bridge (JS camelCase ↔ Rust).

use serde::{Deserialize, Serialize};

/// Options from JS invoke — camelCase (Tauri/serde). Also accepts snake_case
/// alias for `num_speakers` so either side of the bridge works.
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LocalJobOptions {
    pub model: String,
    #[serde(default = "default_lang")]
    pub language: String,
    #[serde(default = "default_true")]
    pub diarize: bool,
    #[serde(default = "default_true")]
    pub punctuate: bool,
    #[serde(default, alias = "num_speakers")]
    pub num_speakers: i32,
    #[serde(default)]
    pub glossary: String,
}

fn default_lang() -> String {
    "vi".into()
}
fn default_true() -> bool {
    true
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_camel_case_num_speakers() {
        let j = r#"{"model":"tiny","language":"vi","diarize":true,"punctuate":true,"numSpeakers":4,"glossary":""}"#;
        let o: LocalJobOptions = serde_json::from_str(j).unwrap();
        assert_eq!(o.num_speakers, 4);
        assert_eq!(o.model, "tiny");
    }

    #[test]
    fn accepts_snake_case_alias() {
        let j = r#"{"model":"small","num_speakers":7}"#;
        let o: LocalJobOptions = serde_json::from_str(j).unwrap();
        assert_eq!(o.num_speakers, 7);
    }

    #[test]
    fn default_num_speakers_zero() {
        let j = r#"{"model":"tiny"}"#;
        let o: LocalJobOptions = serde_json::from_str(j).unwrap();
        assert_eq!(o.num_speakers, 0);
        assert!(o.diarize);
        assert!(o.punctuate);
    }

    #[test]
    fn roundtrip_serialize_camel_case() {
        let o = LocalJobOptions {
            model: "tiny".into(),
            language: "vi".into(),
            diarize: true,
            punctuate: false,
            num_speakers: 3,
            glossary: "foo".into(),
        };
        let v = serde_json::to_value(&o).unwrap();
        assert_eq!(v["numSpeakers"], 3);
        assert_eq!(v["punctuate"], false);
    }
}
