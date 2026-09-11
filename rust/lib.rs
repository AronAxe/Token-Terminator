//! Rust interoperability helpers for [Token Terminator](https://github.com/AronAxe/Token-Terminator).
//!
//! The production Token Terminator runtime remains the Python/Hermes implementation.
//! This crate intentionally exposes only stable cross-language primitives that Rust
//! agent adapters can use without embedding Python: content-addressed artifact
//! identities, digest verification, and the strict character-reduction invariant.
//!
//! It is **not** a PyO3 accelerator and does not implement the SQLite vault,
//! request compiler, tokenizer adapters, or Hermes lifecycle hooks.

#![forbid(unsafe_code)]

use sha2::{Digest, Sha256};
use std::error::Error;
use std::fmt;

/// Number of hexadecimal SHA-256 characters used by Token Terminator's normal
/// short artifact identifier.
pub const SHORT_ARTIFACT_HEX_LEN: usize = 32;

/// A content identity compatible with Token Terminator's Python artifact vault.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ArtifactIdentity {
    /// The normal compact artifact identifier (`a_` plus 32 SHA-256 hex chars).
    pub artifact_id: String,
    /// The complete lowercase SHA-256 digest of the UTF-8 content.
    pub sha256: String,
}

/// Error returned when a caller supplies something that is not a SHA-256 hex digest.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct InvalidSha256;

impl fmt::Display for InvalidSha256 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("expected exactly 64 hexadecimal SHA-256 characters")
    }
}

impl Error for InvalidSha256 {}

fn normalize_sha256(value: &str) -> Result<String, InvalidSha256> {
    if value.len() != 64 || !value.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err(InvalidSha256);
    }
    Ok(value.to_ascii_lowercase())
}

/// Return the lowercase SHA-256 digest of arbitrary bytes.
pub fn sha256_hex(bytes: impl AsRef<[u8]>) -> String {
    let digest = Sha256::digest(bytes.as_ref());
    format!("{digest:x}")
}

/// Compute the normal Token Terminator identity for UTF-8 text.
///
/// The Python vault hashes the exact UTF-8 bytes and normally identifies the
/// artifact as `a_` plus the first 32 hexadecimal characters of that digest.
/// In the astronomically unlikely event of a short-ID collision, the Python
/// vault falls back to the full digest ID; use [`full_artifact_id_from_sha256`]
/// when a host needs that collision form explicitly.
pub fn artifact_identity(content: &str) -> ArtifactIdentity {
    let sha256 = sha256_hex(content.as_bytes());
    let artifact_id = format!("a_{}", &sha256[..SHORT_ARTIFACT_HEX_LEN]);
    ArtifactIdentity {
        artifact_id,
        sha256,
    }
}

/// Build Token Terminator's normal short artifact ID from a full SHA-256 digest.
pub fn artifact_id_from_sha256(sha256: &str) -> Result<String, InvalidSha256> {
    let normalized = normalize_sha256(sha256)?;
    Ok(format!(
        "a_{}",
        &normalized[..SHORT_ARTIFACT_HEX_LEN]
    ))
}

/// Build Token Terminator's full collision-fallback artifact ID from a digest.
pub fn full_artifact_id_from_sha256(sha256: &str) -> Result<String, InvalidSha256> {
    let normalized = normalize_sha256(sha256)?;
    Ok(format!("a_{normalized}"))
}

/// Verify that UTF-8 text has the expected SHA-256 digest.
///
/// Uppercase hexadecimal input is accepted; malformed digests return `false`.
pub fn verify_sha256(content: &str, expected_sha256: &str) -> bool {
    normalize_sha256(expected_sha256)
        .map(|expected| sha256_hex(content.as_bytes()) == expected)
        .unwrap_or(false)
}

/// Return whether an artifact ID is compatible with the supplied UTF-8 text.
///
/// Both the normal short ID and the full collision-fallback ID are accepted.
pub fn artifact_id_matches(content: &str, artifact_id: &str) -> bool {
    let identity = artifact_identity(content);
    artifact_id == identity.artifact_id || artifact_id == format!("a_{}", identity.sha256)
}

/// Mirror Token Terminator's character-based strict-reduction invariant.
///
/// This counts Unicode scalar values instead of UTF-8 bytes so non-ASCII text
/// does not appear artificially larger merely because its encoding uses more
/// than one byte per character. When the Python runtime has an exact tokenizer,
/// it applies an additional token-level gate after this baseline check.
pub fn strictly_smaller_chars(raw: &str, candidate: &str) -> bool {
    candidate.chars().count() < raw.chars().count()
}

#[cfg(test)]
mod tests {
    use super::*;

    const HELLO_SHA256: &str =
        "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824";

    #[test]
    fn identity_matches_python_layout() {
        let identity = artifact_identity("hello");
        assert_eq!(identity.sha256, HELLO_SHA256);
        assert_eq!(identity.artifact_id, "a_2cf24dba5fb0a30e26e83b2ac5b9e29e");
    }

    #[test]
    fn digest_to_short_and_full_ids() {
        assert_eq!(
            artifact_id_from_sha256(HELLO_SHA256).unwrap(),
            "a_2cf24dba5fb0a30e26e83b2ac5b9e29e"
        );
        assert_eq!(
            full_artifact_id_from_sha256(&HELLO_SHA256.to_ascii_uppercase()).unwrap(),
            format!("a_{HELLO_SHA256}")
        );
    }

    #[test]
    fn malformed_digest_is_rejected() {
        assert_eq!(artifact_id_from_sha256("nope"), Err(InvalidSha256));
        assert!(!verify_sha256("hello", "nope"));
    }

    #[test]
    fn verification_and_id_matching_work() {
        assert!(verify_sha256("hello", HELLO_SHA256));
        assert!(artifact_id_matches(
            "hello",
            "a_2cf24dba5fb0a30e26e83b2ac5b9e29e"
        ));
        assert!(artifact_id_matches("hello", &format!("a_{HELLO_SHA256}")));
        assert!(!artifact_id_matches("goodbye", &format!("a_{HELLO_SHA256}")));
    }

    #[test]
    fn strict_smaller_uses_characters_not_utf8_bytes() {
        assert!(strictly_smaller_chars("éé", "é"));
        assert!(!strictly_smaller_chars("é", "é"));
        assert!(!strictly_smaller_chars("é", "ab"));
    }
}
