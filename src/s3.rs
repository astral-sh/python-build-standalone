// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.

use {
    crate::release::build_wanted_filenames,
    anyhow::{Result, anyhow},
    aws_sdk_s3::primitives::ByteStream,
    clap::ArgMatches,
    futures::{StreamExt, TryStreamExt},
    std::{
        collections::BTreeSet,
        path::{Path, PathBuf},
    },
};

/// Maximum number of concurrent S3 uploads.
const UPLOAD_CONCURRENCY: usize = 4;

/// Maximum number of attempts per S3 request (includes the initial attempt).
/// The AWS SDK uses exponential backoff with jitter between attempts.
const S3_MAX_ATTEMPTS: u32 = 5;

/// Upload a single file to S3 under `key`, setting an immutable cache-control header.
async fn upload_s3_file(
    s3: &aws_sdk_s3::Client,
    bucket: &str,
    key: &str,
    path: &Path,
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
    s3.put_object()
        .bucket(bucket)
        .key(key)
        .body(body)
        .cache_control("public, max-age=31536000, immutable")
        .send()
        .await?;
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

    // Upload all files concurrently (up to UPLOAD_CONCURRENCY in-flight at a time).
    let upload_futs = wanted_filenames
        .iter()
        .filter(|(source, _)| filenames.contains(*source))
        .map(|(source, dest)| {
            let s3 = s3.clone();
            let bucket = bucket.clone();
            let key = format!("{prefix}{dest}");
            let path = dist_dir.join(source);
            async move { upload_s3_file(&s3, &bucket, &key, &path, dry_run).await }
        });

    futures::stream::iter(upload_futs)
        .buffer_unordered(UPLOAD_CONCURRENCY)
        .try_collect::<Vec<_>>()
        .await?;

    // Upload the SHA256SUMS file already written (and verified) by upload-release-distributions.
    let shasums_path = dist_dir.join("SHA256SUMS");
    let shasums_key = format!("{prefix}SHA256SUMS");
    upload_s3_file(&s3, bucket, &shasums_key, &shasums_path, dry_run).await?;

    Ok(())
}
