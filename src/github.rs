// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.

use std::str::FromStr;

use {
    crate::release::{
        bootstrap_llvm, produce_install_only, produce_install_only_stripped, RELEASE_TRIPLES,
    },
    anyhow::{anyhow, Result},
    bytes::Bytes,
    clap::ArgMatches,
    futures::StreamExt,
    octocrab::{
        models::{repos::Release, workflows::WorkflowListArtifact},
        params::actions::ArchiveFormat,
        Octocrab, OctocrabBuilder,
    },
    rayon::prelude::*,
    sha2::{Digest, Sha256},
    std::{
        collections::{BTreeMap, BTreeSet, HashMap},
        io::Read,
        path::PathBuf,
    },
    url::Url,
    zip::ZipArchive,
};

async fn fetch_artifact(
    client: &Octocrab,
    org: &str,
    repo: &str,
    artifact: WorkflowListArtifact,
) -> Result<bytes::Bytes> {
    println!("downloading artifact {}", artifact.name);

    let res = client
        .actions()
        .download_artifact(org, repo, artifact.id, ArchiveFormat::Zip)
        .await?;

    Ok(res)
}

async fn upload_release_artifact(
    auth_token: String,
    release: &Release,
    filename: String,
    data: Bytes,
    dry_run: bool,
) -> Result<()> {
    if release.assets.iter().any(|asset| asset.name == filename) {
        println!("release asset {filename} already present; skipping");
        return Ok(());
    }

    let mut url = Url::parse(&release.upload_url)?;
    let path = url.path().to_string();

    if let Some(path) = path.strip_suffix("%7B") {
        url.set_path(path);
    }

    url.query_pairs_mut().clear().append_pair("name", &filename);

    println!("uploading to {url}");

    if dry_run {
        return Ok(());
    }

    // Octocrab doesn't yet support release artifact upload. And the low-level HTTP API
    // forces the use of strings on us. So we have to make our own HTTP client.

    let response = reqwest::Client::builder()
        .build()?
        .put(url)
        .header("Authorization", format!("Bearer {auth_token}"))
        .header("Content-Length", data.len())
        .header("Content-Type", "application/x-tar")
        .body(data)
        .send()
        .await?;

    if !response.status().is_success() {
        return Err(anyhow!("HTTP {}", response.status()));
    }

    Ok(())
}

pub async fn command_fetch_release_distributions(args: &ArgMatches) -> Result<()> {
    let dest_dir = args
        .get_one::<PathBuf>("dest")
        .expect("dest directory should be set");
    let org = args
        .get_one::<String>("organization")
        .expect("organization should be set");
    let repo = args.get_one::<String>("repo").expect("repo should be set");

    let client = OctocrabBuilder::new()
        .personal_token(
            args.get_one::<String>("token")
                .expect("token should be required argument")
                .to_string(),
        )
        .build()?;

    let release_version_range = pep440_rs::VersionSpecifier::from_str(">=3.9")?;

    let workflows = client.workflows(org, repo);

    let mut workflow_names = HashMap::new();

    let workflow_ids = workflows
        .list()
        .send()
        .await?
        .into_iter()
        .filter_map(|wf| {
            if matches!(
                wf.path.as_str(),
                ".github/workflows/darwin.yml"
                    | ".github/workflows/linux.yml"
                    | ".github/workflows/windows.yml"
            ) {
                workflow_names.insert(wf.id, wf.name);

                Some(wf.id)
            } else {
                None
            }
        })
        .collect::<Vec<_>>();

    if workflow_ids.is_empty() {
        return Err(anyhow!(
            "failed to find any workflows; this should not happen"
        ));
    }

    let mut runs: Vec<octocrab::models::workflows::Run> = vec![];

    for workflow_id in workflow_ids {
        let commit = args
            .get_one::<String>("commit")
            .expect("commit should be defined");
        let workflow_name = workflow_names
            .get(&workflow_id)
            .expect("should have workflow name");

        runs.push(
            workflows
                .list_runs(format!("{workflow_id}"))
                .event("push")
                .status("success")
                .send()
                .await?
                .into_iter()
                .find(|run| {
                    run.head_sha.as_str() == commit
                })
                .ok_or_else(|| {
                    anyhow!(
                        "could not find workflow run for commit {commit} for workflow {workflow_name}",
                    )
                })?,
        );
    }

    let mut fs = vec![];

    for run in runs {
        let page = client
            .actions()
            .list_workflow_run_artifacts(org, repo, run.id)
            .send()
            .await?;

        let artifacts = client
            .all_pages::<octocrab::models::workflows::WorkflowListArtifact>(
                page.value.expect("untagged request should have page"),
            )
            .await?;

        for artifact in artifacts {
            if matches!(
                artifact.name.as_str(),
                "pythonbuild" | "sccache" | "toolchain"
            ) || artifact.name.contains("install-only")
            {
                continue;
            }

            fs.push(fetch_artifact(&client, org, repo, artifact));
        }
    }

    let mut buffered = futures::stream::iter(fs).buffer_unordered(24);

    let mut install_paths = vec![];

    while let Some(res) = buffered.next().await {
        let data = res?;

        let mut za = ZipArchive::new(std::io::Cursor::new(data))?;
        for i in 0..za.len() {
            let mut zf = za.by_index(i)?;

            let name = zf.name().to_string();

            let parts = name.split('-').collect::<Vec<_>>();

            if parts[0] != "cpython" {
                println!("ignoring {} not a cpython artifact", name);
                continue;
            };

            let python_version = pep440_rs::Version::from_str(parts[1])?;
            if !release_version_range.contains(&python_version) {
                println!(
                    "{} not in release version range {}",
                    name, release_version_range
                );
                continue;
            }

            // Iterate over `RELEASE_TRIPLES` in reverse-order to ensure that if any triple is a
            // substring of another, the longest match is used.
            let Some((triple, release)) =
                RELEASE_TRIPLES.iter().rev().find_map(|(triple, release)| {
                    if name.contains(triple) {
                        Some((triple, release))
                    } else {
                        None
                    }
                })
            else {
                println!(
                    "ignoring {} does not match any registered release triples",
                    name
                );
                continue;
            };

            let stripped_name = if let Some(s) = name.strip_suffix(".tar.zst") {
                s
            } else {
                println!("ignoring {} not a .tar.zst artifact", name);
                continue;
            };

            let stripped_name = &stripped_name[0..stripped_name.len() - "-YYYYMMDDTHHMM".len()];

            let triple_start = stripped_name
                .find(triple)
                .expect("validated triple presence above");

            let build_suffix = &stripped_name[triple_start + triple.len() + 1..];

            if !release.suffixes(None).any(|suffix| build_suffix == suffix) {
                println!("ignoring {} not a release artifact for triple", name);
                continue;
            }

            let dest_path = dest_dir.join(&name);
            let mut buf = vec![];
            zf.read_to_end(&mut buf)?;
            std::fs::write(&dest_path, &buf)?;

            println!("prepared {} for release", name);

            if build_suffix == release.install_only_suffix {
                install_paths.push(dest_path);
            }
        }
    }

    let llvm_dir = bootstrap_llvm().await?;

    install_paths
        .par_iter()
        .try_for_each(|path| -> Result<()> {
            // Create the `install_only` archive.
            println!(
                "producing install_only archive from {}",
                path.file_name()
                    .expect("should have file name")
                    .to_string_lossy()
            );

            let dest_path = produce_install_only(path)?;

            println!(
                "prepared {} for release",
                dest_path
                    .file_name()
                    .expect("should have file name")
                    .to_string_lossy()
            );

            // Create the `install_only_stripped` archive.
            println!(
                "producing install_only_stripped archive from {}",
                dest_path
                    .file_name()
                    .expect("should have file name")
                    .to_string_lossy()
            );

            let dest_path = produce_install_only_stripped(&dest_path, &llvm_dir)?;

            println!(
                "prepared {} for release",
                dest_path
                    .file_name()
                    .expect("should have file name")
                    .to_string_lossy()
            );

            Ok(())
        })?;

    Ok(())
}

pub async fn command_upload_release_distributions(args: &ArgMatches) -> Result<()> {
    let dist_dir = args
        .get_one::<PathBuf>("dist")
        .expect("dist should be specified");
    let datetime = args
        .get_one::<String>("datetime")
        .expect("datetime should be specified");
    let tag = args
        .get_one::<String>("tag")
        .expect("tag should be specified");
    let ignore_missing = args.get_flag("ignore_missing");
    let token = args
        .get_one::<String>("token")
        .expect("token should be specified")
        .to_string();
    let organization = args
        .get_one::<String>("organization")
        .expect("organization should be specified");
    let repo = args
        .get_one::<String>("repo")
        .expect("repo should be specified");
    let dry_run = args.get_flag("dry_run");

    let mut filenames = std::fs::read_dir(dist_dir)?
        .map(|x| {
            let path = x?.path();
            let filename = path
                .file_name()
                .ok_or_else(|| anyhow!("unable to resolve file name"))?;

            Ok(filename.to_string_lossy().to_string())
        })
        .collect::<Result<Vec<_>>>()?;
    filenames.sort();

    let filenames = filenames
        .into_iter()
        .filter(|x| x.contains(datetime) && x.starts_with("cpython-"))
        .collect::<BTreeSet<_>>();

    let mut python_versions = BTreeSet::new();
    for filename in &filenames {
        let parts = filename.split('-').collect::<Vec<_>>();
        python_versions.insert(parts[1]);
    }

    let mut wanted_filenames = BTreeMap::new();
    for version in python_versions {
        for (triple, release) in RELEASE_TRIPLES.iter() {
            let python_version = pep440_rs::Version::from_str(version)?;
            if let Some(req) = &release.python_version_requirement {
                if !req.contains(&python_version) {
                    continue;
                }
            }

            for suffix in release.suffixes(Some(&python_version)) {
                wanted_filenames.insert(
                    format!(
                        "cpython-{}-{}-{}-{}.tar.zst",
                        version, triple, suffix, datetime
                    ),
                    format!(
                        "cpython-{}+{}-{}-{}-full.tar.zst",
                        version, tag, triple, suffix
                    ),
                );
            }

            wanted_filenames.insert(
                format!(
                    "cpython-{}-{}-install_only-{}.tar.gz",
                    version, triple, datetime
                ),
                format!("cpython-{}+{}-{}-install_only.tar.gz", version, tag, triple),
            );

            wanted_filenames.insert(
                format!(
                    "cpython-{}-{}-install_only_stripped-{}.tar.gz",
                    version, triple, datetime
                ),
                format!(
                    "cpython-{}+{}-{}-install_only_stripped.tar.gz",
                    version, tag, triple
                ),
            );
        }
    }

    let missing = wanted_filenames
        .keys()
        .filter(|x| !filenames.contains(*x))
        .collect::<Vec<_>>();

    for f in &missing {
        println!("missing release artifact: {}", f);
    }
    if missing.is_empty() {
        println!("found all {} release artifacts", wanted_filenames.len());
    } else if !ignore_missing {
        return Err(anyhow!("missing {} release artifacts", missing.len()));
    }

    let client = OctocrabBuilder::new()
        .personal_token(token.clone())
        .build()?;
    let repo_handler = client.repos(organization, repo);
    let releases = repo_handler.releases();

    let release = if let Ok(release) = releases.get_by_tag(tag).await {
        release
    } else {
        return if dry_run {
            println!("release {tag} does not exist; exiting dry-run mode...");
            Ok(())
        } else {
            Err(anyhow!(
                "release {tag} does not exist; create it via GitHub web UI"
            ))
        };
    };

    let mut digests = BTreeMap::new();

    let mut fs = vec![];

    for (source, dest) in wanted_filenames {
        if !filenames.contains(&source) {
            continue;
        }

        let file_data = Bytes::copy_from_slice(&std::fs::read(dist_dir.join(&source))?);

        let mut digest = Sha256::new();
        digest.update(&file_data);

        let digest = hex::encode(digest.finalize());

        digests.insert(dest.clone(), digest.clone());

        fs.push(upload_release_artifact(
            token.clone(),
            &release,
            dest.clone(),
            file_data,
            dry_run,
        ));
        fs.push(upload_release_artifact(
            token.clone(),
            &release,
            format!("{}.sha256", dest),
            Bytes::copy_from_slice(format!("{}\n", digest).as_bytes()),
            dry_run,
        ));
    }

    let mut buffered = futures::stream::iter(fs).buffer_unordered(16);

    while let Some(res) = buffered.next().await {
        res?;
    }

    let shasums = digests
        .iter()
        .map(|(filename, digest)| format!("{}  {}\n", digest, filename))
        .collect::<Vec<_>>()
        .join("");

    std::fs::write(dist_dir.join("SHA256SUMS"), shasums.as_bytes())?;

    upload_release_artifact(
        token.clone(),
        &release,
        "SHA256SUMS".to_string(),
        Bytes::copy_from_slice(shasums.as_bytes()),
        dry_run,
    )
    .await?;

    // Check that content wasn't munged as part of uploading. This once happened
    // and created a busted release. Never again.
    if dry_run {
        println!("skipping SHA256SUMs check");
        return Ok(());
    }

    let release = releases
        .get_by_tag(tag)
        .await
        .map_err(|_| anyhow!("could not find release; this should not happen!"))?;
    let shasums_asset = release
        .assets
        .into_iter()
        .find(|x| x.name == "SHA256SUMS")
        .ok_or_else(|| anyhow!("unable to find SHA256SUMs release asset"))?;

    let mut stream = client
        .repos(organization, repo)
        .releases()
        .stream_asset(shasums_asset.id)
        .await?;

    let mut asset_bytes = Vec::<u8>::new();

    while let Some(chunk) = stream.next().await {
        asset_bytes.extend(chunk?.as_ref());
    }

    if shasums.as_bytes() != asset_bytes {
        return Err(anyhow!("SHA256SUM content mismatch; release might be bad!"));
    }

    Ok(())
}
