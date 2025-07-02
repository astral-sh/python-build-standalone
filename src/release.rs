// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.

use anyhow::Context;
use futures::StreamExt;

use object::FileKind;
use std::{
    process::{Command, Stdio},
    str::FromStr,
};
use url::Url;
use {
    crate::json::parse_python_json,
    anyhow::{anyhow, Result},
    once_cell::sync::Lazy,
    pep440_rs::VersionSpecifier,
    std::{
        collections::BTreeMap,
        io::{BufRead, Read, Write},
        path::{Path, PathBuf},
    },
};

/// Describes a release for a given target triple.
pub struct TripleRelease {
    /// Build suffixes to release.
    pub suffixes: Vec<&'static str>,
    /// Build suffix to use for the `install_only` artifact.
    pub install_only_suffix: &'static str,
    /// Minimum Python version this triple is released for.
    pub python_version_requirement: Option<VersionSpecifier>,
    /// Additional build suffixes to release conditional on the Python version.
    pub conditional_suffixes: Vec<ConditionalSuffixes>,
}

/// Describes additional build suffixes conditional on the Python version.
///
/// e.g., free-threaded builds which are only available for Python 3.13+.
pub struct ConditionalSuffixes {
    /// The minimum Python version to include these suffixes for.
    pub python_version_requirement: VersionSpecifier,
    /// Build suffixes to release.
    pub suffixes: Vec<&'static str>,
}

impl TripleRelease {
    pub fn suffixes<'a>(
        &'a self,
        python_version: Option<&'a pep440_rs::Version>,
    ) -> impl Iterator<Item = &'static str> + 'a {
        self.suffixes
            .iter()
            .copied()
            .chain(
                self.conditional_suffixes
                    .iter()
                    .flat_map(move |conditional| {
                        if python_version.is_none()
                            || python_version.is_some_and(|python_version| {
                                conditional
                                    .python_version_requirement
                                    .contains(python_version)
                            })
                        {
                            conditional.suffixes.iter().copied()
                        } else {
                            [].iter().copied()
                        }
                    }),
            )
    }
}

pub static RELEASE_TRIPLES: Lazy<BTreeMap<&'static str, TripleRelease>> = Lazy::new(|| {
    let mut h = BTreeMap::new();

    // macOS.
    let macos_suffixes = vec!["debug", "pgo+lto"];
    let macos_suffixes_313 = vec!["freethreaded+debug", "freethreaded+pgo+lto"];
    h.insert(
        "aarch64-apple-darwin",
        TripleRelease {
            suffixes: macos_suffixes.clone(),
            install_only_suffix: "pgo+lto",
            python_version_requirement: None,
            conditional_suffixes: vec![ConditionalSuffixes {
                python_version_requirement: VersionSpecifier::from_str(">=3.13.0rc0").unwrap(),
                suffixes: macos_suffixes_313.clone(),
            }],
        },
    );
    h.insert(
        "x86_64-apple-darwin",
        TripleRelease {
            suffixes: macos_suffixes,
            install_only_suffix: "pgo+lto",
            python_version_requirement: None,
            conditional_suffixes: vec![ConditionalSuffixes {
                python_version_requirement: VersionSpecifier::from_str(">=3.13.0rc0").unwrap(),
                suffixes: macos_suffixes_313.clone(),
            }],
        },
    );

    // Windows.
    h.insert(
        "i686-pc-windows-msvc",
        TripleRelease {
            suffixes: vec!["pgo"],
            install_only_suffix: "pgo",
            python_version_requirement: None,
            conditional_suffixes: vec![ConditionalSuffixes {
                python_version_requirement: VersionSpecifier::from_str(">=3.13").unwrap(),
                suffixes: vec!["freethreaded+pgo"],
            }],
        },
    );
    h.insert(
        "x86_64-pc-windows-msvc",
        TripleRelease {
            suffixes: vec!["pgo"],
            install_only_suffix: "pgo",
            python_version_requirement: None,
            conditional_suffixes: vec![ConditionalSuffixes {
                python_version_requirement: VersionSpecifier::from_str(">=3.13").unwrap(),
                suffixes: vec!["freethreaded+pgo"],
            }],
        },
    );
    h.insert(
        "aarch64-pc-windows-msvc",
        TripleRelease {
            suffixes: vec!["pgo"],
            install_only_suffix: "pgo",
            python_version_requirement: Some(VersionSpecifier::from_str(">=3.11").unwrap()),
            conditional_suffixes: vec![ConditionalSuffixes {
                python_version_requirement: VersionSpecifier::from_str(">=3.13").unwrap(),
                suffixes: vec!["freethreaded+pgo"],
            }],
        },
    );

    // Linux.
    let linux_suffixes_pgo = vec!["debug", "pgo+lto"];
    let linux_suffixes_nopgo = vec!["debug", "lto", "noopt"];
    let linux_suffixes_musl = vec![
        "debug",
        "lto",
        "noopt",
        "debug+static",
        "lto+static",
        "noopt+static",
    ];
    let linux_suffixes_musl_freethreaded = vec![
        "freethreaded+debug",
        "freethreaded+lto",
        "freethreaded+noopt",
    ];
    let linux_suffixes_pgo_freethreaded = vec!["freethreaded+debug", "freethreaded+pgo+lto"];
    let linux_suffixes_nopgo_freethreaded = vec![
        "freethreaded+debug",
        "freethreaded+lto",
        "freethreaded+noopt",
    ];

    h.insert(
        "aarch64-unknown-linux-gnu",
        TripleRelease {
            suffixes: linux_suffixes_pgo.clone(),
            install_only_suffix: "pgo+lto",
            python_version_requirement: None,
            conditional_suffixes: vec![ConditionalSuffixes {
                python_version_requirement: VersionSpecifier::from_str(">=3.13").unwrap(),
                suffixes: linux_suffixes_pgo_freethreaded.clone(),
            }],
        },
    );

    h.insert(
        "ppc64le-unknown-linux-gnu",
        TripleRelease {
            suffixes: linux_suffixes_nopgo.clone(),
            install_only_suffix: "lto",
            python_version_requirement: Some(VersionSpecifier::from_str(">=3.9").unwrap()),
            conditional_suffixes: vec![ConditionalSuffixes {
                python_version_requirement: VersionSpecifier::from_str(">=3.13").unwrap(),
                suffixes: linux_suffixes_nopgo_freethreaded.clone(),
            }],
        },
    );

    h.insert(
        "riscv64-unknown-linux-gnu",
        TripleRelease {
            suffixes: linux_suffixes_nopgo.clone(),
            install_only_suffix: "lto",
            python_version_requirement: Some(VersionSpecifier::from_str(">=3.9").unwrap()),
            conditional_suffixes: vec![ConditionalSuffixes {
                python_version_requirement: VersionSpecifier::from_str(">=3.13").unwrap(),
                suffixes: linux_suffixes_nopgo_freethreaded.clone(),
            }],
        },
    );

    h.insert(
        "s390x-unknown-linux-gnu",
        TripleRelease {
            suffixes: linux_suffixes_nopgo.clone(),
            install_only_suffix: "lto",
            python_version_requirement: Some(VersionSpecifier::from_str(">=3.9").unwrap()),
            conditional_suffixes: vec![ConditionalSuffixes {
                python_version_requirement: VersionSpecifier::from_str(">=3.13").unwrap(),
                suffixes: linux_suffixes_nopgo_freethreaded.clone(),
            }],
        },
    );

    h.insert(
        "armv7-unknown-linux-gnueabi",
        TripleRelease {
            suffixes: linux_suffixes_nopgo.clone(),
            install_only_suffix: "lto",
            python_version_requirement: Some(VersionSpecifier::from_str(">=3.9").unwrap()),
            conditional_suffixes: vec![ConditionalSuffixes {
                python_version_requirement: VersionSpecifier::from_str(">=3.13").unwrap(),
                suffixes: linux_suffixes_nopgo_freethreaded.clone(),
            }],
        },
    );

    h.insert(
        "armv7-unknown-linux-gnueabihf",
        TripleRelease {
            suffixes: linux_suffixes_nopgo.clone(),
            install_only_suffix: "lto",
            python_version_requirement: Some(VersionSpecifier::from_str(">=3.9").unwrap()),
            conditional_suffixes: vec![ConditionalSuffixes {
                python_version_requirement: VersionSpecifier::from_str(">=3.13").unwrap(),
                suffixes: linux_suffixes_nopgo_freethreaded.clone(),
            }],
        },
    );

    h.insert(
        "x86_64-unknown-linux-gnu",
        TripleRelease {
            suffixes: linux_suffixes_pgo.clone(),
            install_only_suffix: "pgo+lto",
            python_version_requirement: None,
            conditional_suffixes: vec![ConditionalSuffixes {
                python_version_requirement: VersionSpecifier::from_str(">=3.13").unwrap(),
                suffixes: linux_suffixes_pgo_freethreaded.clone(),
            }],
        },
    );
    h.insert(
        "x86_64_v2-unknown-linux-gnu",
        TripleRelease {
            suffixes: linux_suffixes_pgo.clone(),
            install_only_suffix: "pgo+lto",
            python_version_requirement: Some(VersionSpecifier::from_str(">=3.9").unwrap()),
            conditional_suffixes: vec![ConditionalSuffixes {
                python_version_requirement: VersionSpecifier::from_str(">=3.13").unwrap(),
                suffixes: linux_suffixes_pgo_freethreaded.clone(),
            }],
        },
    );
    h.insert(
        "x86_64_v3-unknown-linux-gnu",
        TripleRelease {
            suffixes: linux_suffixes_pgo.clone(),
            install_only_suffix: "pgo+lto",
            python_version_requirement: Some(VersionSpecifier::from_str(">=3.9").unwrap()),
            conditional_suffixes: vec![ConditionalSuffixes {
                python_version_requirement: VersionSpecifier::from_str(">=3.13").unwrap(),
                suffixes: linux_suffixes_pgo_freethreaded.clone(),
            }],
        },
    );
    h.insert(
        "x86_64_v4-unknown-linux-gnu",
        TripleRelease {
            suffixes: linux_suffixes_pgo.clone(),
            install_only_suffix: "pgo+lto",
            python_version_requirement: Some(VersionSpecifier::from_str(">=3.9").unwrap()),
            conditional_suffixes: vec![ConditionalSuffixes {
                python_version_requirement: VersionSpecifier::from_str(">=3.13").unwrap(),
                suffixes: linux_suffixes_pgo_freethreaded.clone(),
            }],
        },
    );
    h.insert(
        "x86_64-unknown-linux-musl",
        TripleRelease {
            suffixes: linux_suffixes_musl.clone(),
            install_only_suffix: "lto",
            python_version_requirement: None,
            conditional_suffixes: vec![ConditionalSuffixes {
                python_version_requirement: VersionSpecifier::from_str(">=3.13").unwrap(),
                suffixes: linux_suffixes_musl_freethreaded.clone(),
            }],
        },
    );
    h.insert(
        "x86_64_v2-unknown-linux-musl",
        TripleRelease {
            suffixes: linux_suffixes_musl.clone(),
            install_only_suffix: "lto",
            python_version_requirement: None,
            conditional_suffixes: vec![ConditionalSuffixes {
                python_version_requirement: VersionSpecifier::from_str(">=3.13").unwrap(),
                suffixes: linux_suffixes_musl_freethreaded.clone(),
            }],
        },
    );
    h.insert(
        "x86_64_v3-unknown-linux-musl",
        TripleRelease {
            suffixes: linux_suffixes_musl.clone(),
            install_only_suffix: "lto",
            python_version_requirement: None,
            conditional_suffixes: vec![ConditionalSuffixes {
                python_version_requirement: VersionSpecifier::from_str(">=3.13").unwrap(),
                suffixes: linux_suffixes_musl_freethreaded.clone(),
            }],
        },
    );
    h.insert(
        "x86_64_v4-unknown-linux-musl",
        TripleRelease {
            suffixes: linux_suffixes_musl.clone(),
            install_only_suffix: "lto",
            python_version_requirement: None,
            conditional_suffixes: vec![ConditionalSuffixes {
                python_version_requirement: VersionSpecifier::from_str(">=3.13").unwrap(),
                suffixes: linux_suffixes_musl_freethreaded.clone(),
            }],
        },
    );

    h
});

/// Convert a .tar.zst archive to an install-only .tar.gz archive.
pub fn convert_to_install_only<W: Write>(reader: impl BufRead, writer: W) -> Result<W> {
    let dctx = zstd::stream::Decoder::new(reader)?;

    let mut tar_in = tar::Archive::new(dctx);

    let writer = flate2::write::GzEncoder::new(writer, flate2::Compression::default());

    let mut builder = tar::Builder::new(writer);

    let mut entries = tar_in.entries()?;

    // First entry in archive should be python/PYTHON.json.
    let mut entry = entries.next().expect("tar must have content")?;
    if entry.path_bytes().as_ref() != b"python/PYTHON.json" {
        return Err(anyhow!("first archive entry not PYTHON.json"));
    }

    let mut json_data = vec![];
    entry.read_to_end(&mut json_data)?;

    let json_main = parse_python_json(&json_data).context("failed to parse PYTHON.json")?;

    let stdlib_path = json_main
        .python_paths
        .get("stdlib")
        .expect("stdlib entry expected");

    for entry in entries {
        let mut entry = entry?;

        let path_bytes = entry.path_bytes();

        if !path_bytes.starts_with(b"python/install/") {
            continue;
        }

        // Strip the libpython static library, as it significantly
        // increases the size of the archive and isn't needed in most cases.
        if path_bytes
            .windows(b"/libpython".len())
            .any(|x| x == b"/libpython")
            && path_bytes.ends_with(b".a")
        {
            continue;
        }

        // Strip standard library test modules, as they aren't needed in regular
        // installs. We do this based on the metadata in PYTHON.json for
        // consistency.
        if json_main
            .python_stdlib_test_packages
            .iter()
            .any(|test_package| {
                let package_path =
                    format!("python/{}/{}/", stdlib_path, test_package.replace('.', "/"));

                path_bytes.starts_with(package_path.as_bytes())
            })
        {
            continue;
        }

        let mut data = vec![];
        entry.read_to_end(&mut data)?;

        let path = entry.path()?;
        let new_path = PathBuf::from("python").join(path.strip_prefix("python/install/")?);

        let mut header = entry.header().clone();
        header.set_path(&new_path)?;
        header.set_cksum();

        builder.append(&header, std::io::Cursor::new(data))?;
    }

    Ok(builder.into_inner()?.finish()?)
}

/// Run `llvm-strip` over the given data, returning the stripped data.
fn llvm_strip(data: &[u8], llvm_dir: &Path) -> Result<Vec<u8>> {
    let mut command = Command::new(llvm_dir.join("bin/llvm-strip"))
        .arg("--strip-debug")
        .arg("-")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .with_context(|| "failed to spawn llvm-strip")?;

    command
        .stdin
        .as_mut()
        .unwrap()
        .write_all(data)
        .with_context(|| "failed to write data to llvm-strip")?;

    let output = command
        .wait_with_output()
        .with_context(|| "failed to wait for llvm-strip")?;
    if !output.status.success() {
        return Err(anyhow!("llvm-strip failed: {}", output.status));
    }

    Ok(output.stdout)
}

/// Given an install-only .tar.gz archive, strip the underlying build.
pub fn convert_to_stripped<W: Write>(
    reader: impl BufRead,
    writer: W,
    llvm_dir: &Path,
) -> Result<W> {
    let dctx = flate2::read::GzDecoder::new(reader);

    let mut tar_in = tar::Archive::new(dctx);

    let writer = flate2::write::GzEncoder::new(writer, flate2::Compression::default());

    let mut builder = tar::Builder::new(writer);

    for entry in tar_in.entries()? {
        let mut entry = entry?;

        let mut data = vec![];
        entry.read_to_end(&mut data)?;

        let path = entry.path()?;

        // Drop PDB files.
        match pdb::PDB::open(std::io::Cursor::new(&data)) {
            Ok(_) => {
                continue;
            }
            Err(err) => {
                if path.extension().is_some_and(|ext| ext == "pdb") {
                    println!(
                        "file with `.pdb` extension ({}) failed to parse as PDB :{err}",
                        path.display()
                    );
                }
            }
        }

        // If we have an ELF, Mach-O, or PE file, strip it in-memory with `llvm-strip`, and
        // return the stripped data.
        if matches!(
            FileKind::parse(data.as_slice()),
            Ok(FileKind::Elf32
                | FileKind::Elf64
                | FileKind::MachO32
                | FileKind::MachO64
                | FileKind::MachOFat32
                | FileKind::MachOFat64
                | FileKind::Pe32
                | FileKind::Pe64)
        ) {
            data = llvm_strip(&data, llvm_dir)
                .with_context(|| format!("failed to strip {}", path.display()))?;
        }

        let mut header = entry.header().clone();
        header.set_size(data.len() as u64);
        header.set_cksum();

        builder.append(&header, std::io::Cursor::new(data))?;
    }

    Ok(builder.into_inner()?.finish()?)
}

/// Create an install-only .tar.gz archive from a .tar.zst archive.
pub fn produce_install_only(tar_zst_path: &Path) -> Result<PathBuf> {
    let buf = std::fs::read(tar_zst_path)?;

    let gz_data = convert_to_install_only(std::io::Cursor::new(buf), std::io::Cursor::new(vec![]))
        .context(format!(
            "failed to convert `{}` to install_only",
            tar_zst_path.display()
        ))?
        .into_inner();

    let filename = tar_zst_path
        .file_name()
        .expect("should have filename")
        .to_string_lossy();

    let mut name_parts = filename
        .split('-')
        .map(|x| x.to_string())
        .collect::<Vec<_>>();
    let parts_len = name_parts.len();

    name_parts[parts_len - 2] = "install_only".to_string();

    let install_only_name = name_parts.join("-");
    let install_only_name = install_only_name.replace(".tar.zst", ".tar.gz");

    let dest_path = tar_zst_path.with_file_name(install_only_name);
    std::fs::write(&dest_path, gz_data)?;

    Ok(dest_path)
}

pub fn produce_install_only_stripped(tar_gz_path: &Path, llvm_dir: &Path) -> Result<PathBuf> {
    let buf = std::fs::read(tar_gz_path)?;

    let size_before = buf.len();

    let gz_data = convert_to_stripped(
        std::io::Cursor::new(buf),
        std::io::Cursor::new(vec![]),
        llvm_dir,
    )
    .context(format!(
        "failed to convert `{}` to install_only_stripped",
        tar_gz_path.display()
    ))?
    .into_inner();

    let size_after = gz_data.len();

    println!(
        "stripped {} from {size_before} to {size_after} bytes",
        tar_gz_path.display()
    );

    // Given `cpython-3.12.4-x86_64_v3-unknown-linux-gnu-install_only-20240722T0909.tar.gz`,
    // map to `cpython-3.12.4-x86_64_v3-unknown-linux-gnu-install_only_stripped-20240722T0909.tar.gz`.
    let filename = tar_gz_path
        .file_name()
        .expect("should have filename")
        .to_string_lossy();

    let mut name_parts = filename
        .split('-')
        .map(|x| x.to_string())
        .collect::<Vec<_>>();
    let parts_len = name_parts.len();

    name_parts[parts_len - 2] = "install_only_stripped".to_string();

    let install_only_name = name_parts.join("-");

    let dest_path = tar_gz_path.with_file_name(install_only_name);
    std::fs::write(&dest_path, gz_data)?;

    Ok(dest_path)
}

/// URL from which to download LLVM.
///
/// To be kept in sync with `pythonbuild/downloads.py`.
static LLVM_URL: Lazy<Url> = Lazy::new(|| {
    if cfg!(target_os = "macos") {
        if std::env::consts::ARCH == "aarch64" {
            Url::parse("https://github.com/indygreg/toolchain-tools/releases/download/toolchain-bootstrap%2F20250511/llvm-20.1.4+20250511-aarch64-apple-darwin.tar.zst").unwrap()
        } else if std::env::consts::ARCH == "x86_64" {
            Url::parse("https://github.com/indygreg/toolchain-tools/releases/download/toolchain-bootstrap%2F20250511/llvm-20.1.4+20250511-x86_64-apple-darwin.tar.zst").unwrap()
        } else {
            panic!("unsupported macOS architecture");
        }
    } else if cfg!(target_os = "linux") {
        Url::parse("https://github.com/indygreg/toolchain-tools/releases/download/toolchain-bootstrap%2F20250511/llvm-20.1.4+20250511-gnu_only-x86_64-unknown-linux-gnu.tar.zst").unwrap()
    } else {
        panic!("unsupported platform");
    }
});

/// Bootstrap `llvm` for the current platform.
///
/// Returns the path to the top-level `llvm` directory.
pub async fn bootstrap_llvm() -> Result<PathBuf> {
    let url = &*LLVM_URL;
    let filename = url.path_segments().unwrap().last().unwrap();

    let llvm_dir = Path::new("build").join("llvm");
    std::fs::create_dir_all(&llvm_dir)?;

    // If `llvm` is already available with the target version, return it.
    if llvm_dir.join(filename).exists() {
        return Ok(llvm_dir.join("llvm"));
    }

    println!("Downloading LLVM tarball from: {url}");

    // Create a temporary directory to download and extract the LLVM tarball.
    let temp_dir = tempfile::TempDir::new()?;

    // Download the tarball.
    let tarball_path = temp_dir
        .path()
        .join(url.path_segments().unwrap().last().unwrap());
    let mut tarball_file = tokio::fs::File::create(&tarball_path).await?;
    let mut bytes_stream = reqwest::Client::new()
        .get(url.clone())
        .send()
        .await?
        .bytes_stream();
    while let Some(chunk) = bytes_stream.next().await {
        tokio::io::copy(&mut chunk?.as_ref(), &mut tarball_file).await?;
    }

    // Decompress the tarball.
    let tarball = std::fs::File::open(&tarball_path)?;
    let tar = zstd::stream::Decoder::new(std::io::BufReader::new(tarball))?;
    let mut archive = tar::Archive::new(tar);
    archive.unpack(temp_dir.path())?;

    // Persist the directory.
    match tokio::fs::remove_dir_all(&llvm_dir).await {
        Ok(_) => {}
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => {}
        Err(err) => return Err(err).context("failed to remove existing llvm directory"),
    }
    tokio::fs::rename(temp_dir.into_path(), &llvm_dir).await?;

    Ok(llvm_dir.join("llvm"))
}
