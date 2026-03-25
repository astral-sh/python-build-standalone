// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.

use {
    crate::release::build_wanted_filenames,
    anyhow::{Result, anyhow, ensure},
    aws_sdk_s3::primitives::ByteStream,
    base64::{Engine as _, engine::general_purpose::STANDARD as BASE64},
    clap::ArgMatches,
    futures::{StreamExt, TryStreamExt},
    sha2::{Digest, Sha256},
    std::{
        collections::{BTreeMap, BTreeSet},
        path::{Path, PathBuf},
    },
};

/// Maximum number of concurrent S3 uploads.
const UPLOAD_CONCURRENCY: usize = 4;

/// Maximum number of attempts per S3 request (includes the initial attempt).
/// The AWS SDK uses exponential backoff with jitter between attempts.
const S3_MAX_ATTEMPTS: u32 = 5;

/// A validated SHA-256 checksum.
#[derive(Clone, Debug, Eq, PartialEq)]
struct Sha256Sum([u8; 32]);

impl Sha256Sum {
    fn from_bytes(bytes: [u8; 32]) -> Self {
        Self(bytes)
    }

    fn to_base64(&self) -> String {
        BASE64.encode(self.0)
    }
}

impl TryFrom<&str> for Sha256Sum {
    type Error = anyhow::Error;

    fn try_from(hex_digest: &str) -> Result<Self> {
        let bytes = hex::decode(hex_digest)?;
        let bytes: [u8; 32] = bytes
            .try_into()
            .map_err(|_| anyhow!("expected 32-byte sha256 digest"))?;
        Ok(Self(bytes))
    }
}

/// Parse a `SHA256SUMS` file into a map of filename → digest.
fn parse_sha256sums(content: &str) -> Result<BTreeMap<String, Sha256Sum>> {
    let mut digests = BTreeMap::new();

    for (line_no, line) in content.lines().enumerate() {
        let (digest, filename) = line
            .split_once("  ")
            .ok_or_else(|| anyhow!("malformed SHA256SUMS line {}", line_no + 1))?;
        ensure!(
            !filename.is_empty(),
            "missing filename on SHA256SUMS line {}",
            line_no + 1
        );
        let digest = Sha256Sum::try_from(digest)?;
        ensure!(
            digests.insert(filename.to_string(), digest).is_none(),
            "duplicate filename in SHA256SUMS: {filename}"
        );
    }

    Ok(digests)
}

fn ensure_sha256sums_coverage(
    wanted_filenames: &BTreeMap<String, String>,
    present_filenames: &BTreeSet<String>,
    sha256_digests: &BTreeMap<String, Sha256Sum>,
) -> Result<()> {
    let missing = wanted_filenames
        .iter()
        .filter(|(source, _)| present_filenames.contains(*source))
        .map(|(_, dest)| dest)
        .filter(|dest| !sha256_digests.contains_key(*dest))
        .collect::<Vec<_>>();

    if missing.is_empty() {
        Ok(())
    } else {
        Err(anyhow!(
            "SHA256SUMS missing {} entries; first missing artifact: {}",
            missing.len(),
            missing[0]
        ))
    }
}

/// Upload a single file to S3 under `key`, setting an immutable cache-control header.
///
/// When `sha256` is provided the SHA-256 content checksum is included in the
/// PUT request so that S3 verifies data integrity on receipt.
async fn upload_s3_file(
    s3: &aws_sdk_s3::Client,
    bucket: &str,
    key: &str,
    path: &Path,
    sha256: Option<&Sha256Sum>,
    dry_run: bool,
) -> Result<()> {
    println!(
        "uploading {} -> s3://{bucket}/{key}",
        path.file_name()
            .expect("path should have a file name")
            .to_string_lossy()
    );
    if dry_run {
        return Ok(());
    }
    // A single PUT is sufficient here: individual artifacts are well under the 5 GB
    // single-request limit, and we already upload up to UPLOAD_CONCURRENCY files
    // concurrently, so splitting each file into multipart chunks would add complexity
    // without meaningfully improving throughput.
    let body = ByteStream::from_path(path).await?;
    let mut req = s3
        .put_object()
        .bucket(bucket)
        .key(key)
        .body(body)
        .cache_control("public, max-age=31536000, immutable");

    if let Some(digest) = sha256 {
        req = req.checksum_sha256(digest.to_base64());
    }

    req.send().await?;
    Ok(())
}

pub async fn command_upload_mirror_distributions(args: &ArgMatches) -> Result<()> {
    let dist_dir = args
        .get_one::<PathBuf>("dist")
        .expect("dist should be specified");
    let datetime = args
        .get_one::<String>("datetime")
        .expect("datetime should be specified");
    let tag = args
        .get_one::<String>("tag")
        .expect("tag should be specified");
    let bucket = args
        .get_one::<String>("bucket")
        .expect("bucket should be specified");
    let prefix = args
        .get_one::<String>("prefix")
        .cloned()
        .unwrap_or_default();
    let dry_run = args.get_flag("dry_run");
    let ignore_missing = args.get_flag("ignore_missing");

    // Collect and filter the filenames present in dist/.
    let mut all_filenames = std::fs::read_dir(dist_dir)?
        .map(|entry| {
            let path = entry?.path();
            let filename = path
                .file_name()
                .ok_or_else(|| anyhow!("unable to resolve file name"))?;
            Ok(filename.to_string_lossy().to_string())
        })
        .collect::<Result<Vec<_>>>()?;
    all_filenames.sort();

    let filenames = all_filenames
        .into_iter()
        .filter(|x| x.contains(datetime) && x.starts_with("cpython-"))
        .collect::<BTreeSet<_>>();

    let wanted_filenames = build_wanted_filenames(&filenames, datetime, tag)?;

    // Report any missing artifacts.
    let missing = wanted_filenames
        .keys()
        .filter(|x| !filenames.contains(*x))
        .collect::<Vec<_>>();
    for f in &missing {
        println!("missing release artifact: {f}");
    }
    if missing.is_empty() {
        println!("found all {} release artifacts", wanted_filenames.len());
    } else if !ignore_missing {
        return Err(anyhow!("missing {} release artifacts", missing.len()));
    }

    // Initialise the AWS S3 client. Credentials and endpoint are read from the standard
    // AWS environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,
    // AWS_ENDPOINT_URL, AWS_DEFAULT_REGION).
    let retry_config =
        aws_sdk_s3::config::retry::RetryConfig::standard().with_max_attempts(S3_MAX_ATTEMPTS);
    let config = aws_config::load_defaults(aws_config::BehaviorVersion::latest()).await;
    let s3_config = aws_sdk_s3::config::Builder::from(&config)
        .retry_config(retry_config)
        .build();
    let s3 = aws_sdk_s3::Client::from_conf(s3_config);

    let shasums_path = dist_dir.join("SHA256SUMS");

    // Parse SHA256SUMS (written and verified by upload-release-distributions) so
    // we can supply a content checksum on every PUT. S3 will reject the upload if
    // the data it receives does not match, guarding against silent corruption.
    // In dry-run mode we skip reading the file entirely so the command can still be
    // used to validate naming and missing-artifact handling on a fresh dist/.
    let shasums_content = if dry_run {
        None
    } else {
        Some(std::fs::read_to_string(&shasums_path)?)
    };
    let sha256_digests = if let Some(content) = &shasums_content {
        let sha256_digests = parse_sha256sums(content)?;
        ensure_sha256sums_coverage(&wanted_filenames, &filenames, &sha256_digests)?;
        sha256_digests
    } else {
        BTreeMap::new()
    };

    // Upload all files concurrently (up to UPLOAD_CONCURRENCY in-flight at a time).
    let upload_futs = wanted_filenames
        .iter()
        .filter(|(source, _)| filenames.contains(*source))
        .map(|(source, dest)| {
            let s3 = s3.clone();
            let bucket = bucket.clone();
            let key = format!("{prefix}{dest}");
            let path = dist_dir.join(source);
            let sha256 = sha256_digests.get(dest).cloned();
            async move { upload_s3_file(&s3, &bucket, &key, &path, sha256.as_ref(), dry_run).await }
        });

    futures::stream::iter(upload_futs)
        .buffer_unordered(UPLOAD_CONCURRENCY)
        .try_collect::<Vec<_>>()
        .await?;

    // Upload the SHA256SUMS file itself, computing its digest on the fly.
    let shasums_sha256 = shasums_content.as_ref().map(|content| {
        let mut hasher = Sha256::new();
        hasher.update(content.as_bytes());
        Sha256Sum::from_bytes(hasher.finalize().into())
    });
    let shasums_key = format!("{prefix}SHA256SUMS");
    upload_s3_file(
        &s3,
        bucket,
        &shasums_key,
        &shasums_path,
        shasums_sha256.as_ref(),
        dry_run,
    )
    .await?;

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{Sha256Sum, ensure_sha256sums_coverage, parse_sha256sums};
    use std::collections::{BTreeMap, BTreeSet};

    #[test]
    fn sha256_sum_rejects_non_sha256_lengths() {
        assert!(Sha256Sum::try_from("abcd").is_err());
    }

    #[test]
    fn parse_sha256sums_rejects_malformed_lines() {
        assert!(parse_sha256sums("not-a-valid-line\n").is_err());
    }

    #[test]
    fn ensure_sha256sums_coverage_requires_every_uploaded_artifact() {
        let wanted_filenames =
            BTreeMap::from([("source.tar.zst".to_string(), "dest.tar.zst".to_string())]);
        let present_filenames = BTreeSet::from(["source.tar.zst".to_string()]);
        let sha256_digests = BTreeMap::new();

        assert!(
            ensure_sha256sums_coverage(&wanted_filenames, &present_filenames, &sha256_digests)
                .is_err()
        );
    }
}
