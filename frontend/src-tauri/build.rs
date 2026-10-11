#[path = "src/build_config.rs"]
mod build_config;

fn main() {
    let manifest = std::path::PathBuf::from(std::env::var_os("CARGO_MANIFEST_DIR").unwrap());
    let dotenv = manifest.join("../../.env");
    println!("cargo:rerun-if-changed={}", dotenv.display());
    println!("cargo:rerun-if-changed=src/build_config.rs");
    println!("cargo:rerun-if-env-changed=ORION_LOCAL_TOKEN");
    // Match the Python backend's .env override behavior. Never print the value.
    let token = match std::fs::read_to_string(&dotenv) {
        Ok(contents) => build_config::local_token(&contents),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => None,
        Err(_) => panic!("Cannot read the project's .env for desktop configuration"),
    }
    .or_else(|| {
        std::env::var("ORION_LOCAL_TOKEN")
            .ok()
            .filter(|value| !value.trim().is_empty())
    })
    .expect(
        "Set ORION_LOCAL_TOKEN in the root .env or build environment before building ORION Desktop",
    );
    let output = std::path::PathBuf::from(std::env::var_os("OUT_DIR").unwrap());
    std::fs::write(output.join("orion-local-token.txt"), token.trim())
        .expect("Cannot prepare desktop connection configuration");
    tauri_build::build()
}
