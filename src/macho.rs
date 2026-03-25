// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.

use {
    crate::validation::ValidationContext,
    anyhow::{Context, Result, anyhow},
    apple_sdk::{AppleSdk, SdkSearch, SdkSearchLocation, SdkSorting, SdkVersion, SimpleSdk},
    semver::Version,
    std::{
        collections::{BTreeMap, BTreeSet},
        convert::TryFrom,
        path::{Path, PathBuf},
        str::FromStr,
    },
    text_stub_library::TbdVersionedRecord,
};

#[derive(Clone, Debug, PartialEq, PartialOrd)]
pub struct MachOPackedVersion {
    value: u32,
}

impl TryFrom<&str> for MachOPackedVersion {
    type Error = anyhow::Error;

    fn try_from(value: &str) -> Result<Self, Self::Error> {
        let parts = value.split('.').collect::<Vec<_>>();

        if parts.len() != 3 {
            return Err(anyhow!("packed version must have 3 components"));
        }

        let major = u32::from_str(parts[0])?;
        let minor = u32::from_str(parts[1])?;
        let subminor = u32::from_str(parts[2])?;

        let value = (major << 16) | ((minor & 0xff) << 8) | (subminor & 0xff);

        Ok(Self { value })
    }
}

impl From<u32> for MachOPackedVersion {
    fn from(value: u32) -> Self {
        Self { value }
    }
}

impl std::fmt::Display for MachOPackedVersion {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let major = self.value >> 16;
        let minor = (self.value >> 8) & 0xff;
        let subminor = self.value & 0xff;

        f.write_str(&format!("{major}.{minor}.{subminor}"))
    }
}

/// Describes a mach-o dylib that can be loaded by a distribution.
#[derive(Clone, Debug, PartialEq)]
pub struct MachOAllowedDylib {
    /// Name of the dylib.
    ///
    /// Typically an absolute filesystem path.
    pub name: String,

    /// Maximum compatibility version that can be referenced.
    pub max_compatibility_version: MachOPackedVersion,

    /// Whether the loading of this dylib must be present in the distribution.
    pub required: bool,
}

/// Holds required symbols defined in a library.
#[derive(Clone, Debug, Default)]
pub struct LibrarySymbols {
    /// Symbol name -> source paths that require them.
    pub symbols: BTreeMap<String, BTreeSet<PathBuf>>,
}

impl LibrarySymbols {
    /// Obtain all paths referenced in this collection.
    pub fn all_paths(&self) -> BTreeSet<PathBuf> {
        let mut res = BTreeSet::new();

        for paths in self.symbols.values() {
            res.extend(paths.iter().cloned());
        }

        res
    }
}

/// Holds required symbols, indexed by library.
#[derive(Clone, Debug, Default)]
pub struct RequiredSymbols {
    pub libraries: BTreeMap<String, LibrarySymbols>,
}

impl RequiredSymbols {
    /// Register a required symbol.
    ///
    /// `library` is the library that `symbol` is defined in. And `path` is the path needing
    /// this symbol.
    pub fn insert(&mut self, library: impl ToString, symbol: impl ToString, path: PathBuf) {
        self.libraries
            .entry(library.to_string())
            .or_default()
            .symbols
            .entry(symbol.to_string())
            .or_default()
            .insert(path);
    }

    /// Merge the contents of another instance into this one.
    pub fn merge(&mut self, other: Self) {
        for (library, symbols) in other.libraries {
            let entry = self.libraries.entry(library).or_default();

            for (name, paths) in symbols.symbols {
                entry.symbols.entry(name).or_default().extend(paths);
            }
        }
    }
}

fn tbd_relative_path(path: &str) -> Result<String> {
    if let Some(stripped) = path.strip_prefix('/') {
        if let Some(stem) = stripped.strip_suffix(".dylib") {
            Ok(format!("{stem}.tbd"))
        } else {
            Ok(format!("{stripped}.tbd"))
        }
    } else {
        Err(anyhow!("could not determine tbd path from {}", path))
    }
}

#[derive(Default, Debug)]
struct TbdMetadata {
    symbols: BTreeMap<String, BTreeSet<String>>,
    weak_symbols: BTreeMap<String, BTreeSet<String>>,
    re_export_paths: BTreeMap<String, BTreeSet<String>>,
}

impl TbdMetadata {
    fn from_path(path: &Path) -> Result<Self> {
        let data = std::fs::read_to_string(path)?;

        let mut res = Self::default();

        let process_export_v12 =
            |res: &mut Self, export: text_stub_library::yaml::TbdVersion12ExportSection| {
                for arch in export.archs {
                    res.symbols
                        .entry(format!("{}-macos", arch.clone()))
                        .or_default()
                        .extend(
                            export
                                .symbols
                                .iter()
                                .cloned()
                                .chain(
                                    export
                                        .objc_classes
                                        .iter()
                                        .map(|cls| format!("_OBJC_CLASS_${cls}")),
                                )
                                .chain(
                                    export
                                        .objc_classes
                                        .iter()
                                        .map(|cls| format!("_OBJC_METACLASS_${cls}")),
                                ),
                        );

                    res.weak_symbols
                        .entry(format!("{}-macos", arch.clone()))
                        .or_default()
                        .extend(export.weak_def_symbols.iter().cloned());

                    res.re_export_paths
                        .entry(format!("{}-macos", arch.clone()))
                        .or_default()
                        .extend(export.re_exports.iter().cloned());
                }
            };

        for record in text_stub_library::parse_str(&data)? {
            match record {
                TbdVersionedRecord::V1(record) => {
                    for export in record.exports {
                        process_export_v12(&mut res, export);
                    }
                }
                TbdVersionedRecord::V2(record) => {
                    for export in record.exports {
                        process_export_v12(&mut res, export);
                    }
                }
                TbdVersionedRecord::V3(record) => {
                    for export in record.exports {
                        for arch in export.archs {
                            res.symbols
                                .entry(format!("{}-macos", arch.clone()))
                                .or_default()
                                .extend(
                                    export
                                        .symbols
                                        .iter()
                                        .cloned()
                                        .chain(
                                            export
                                                .objc_classes
                                                .iter()
                                                .map(|cls| format!("_OBJC_CLASS_$_{cls}")),
                                        )
                                        .chain(
                                            export
                                                .objc_classes
                                                .iter()
                                                .map(|cls| format!("_OBJC_METACLASS_$_{cls}")),
                                        ),
                                );

                            res.weak_symbols
                                .entry(format!("{}-macos", arch.clone()))
                                .or_default()
                                .extend(export.weak_def_symbols.iter().cloned());

                            // In version 3 records, re-exports is a list of filenames.
                            res.re_export_paths
                                .entry(format!("{}-macos", arch.clone()))
                                .or_default()
                                .extend(export.re_exports.iter().cloned());
                        }
                    }
                }
                TbdVersionedRecord::V4(record) => {
                    for export in record.exports {
                        for target in export.targets {
                            res.symbols.entry(target.clone()).or_default().extend(
                                export
                                    .symbols
                                    .iter()
                                    .cloned()
                                    .chain(
                                        export
                                            .objc_classes
                                            .iter()
                                            .map(|cls| format!("_OBJC_CLASS_$_{cls}")),
                                    )
                                    .chain(
                                        export
                                            .objc_classes
                                            .iter()
                                            .map(|cls| format!("_OBJC_METACLASS_$_{cls}")),
                                    ),
                            );
                            res.weak_symbols
                                .entry(target)
                                .or_default()
                                .extend(export.weak_symbols.iter().cloned());
                        }
                    }
                    for export in record.re_exports {
                        for target in export.targets {
                            res.symbols
                                .entry(target.clone())
                                .or_default()
                                .extend(export.symbols.iter().cloned());
                            res.weak_symbols
                                .entry(target.clone())
                                .or_default()
                                .extend(export.weak_symbols.iter().cloned());
                        }
                    }
                }
            }
        }

        // Time for some hacks!

        // Some SDKs have a `R8289209$` prefix on symbol names. We have no clue what this
        // is for. But we need to strip it for symbol references to resolve properly.
        for (_, symbols) in res.symbols.iter_mut() {
            let stripped = symbols
                .iter()
                .filter_map(|x| {
                    x.strip_prefix("R8289209$")
                        .map(|stripped| stripped.to_string())
                })
                .collect::<Vec<_>>();

            symbols.extend(stripped);
        }

        Ok(res)
    }

    fn expand_file_references(&mut self, root_path: &Path) -> Result<()> {
        let mut extra_symbols: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();

        for (target, paths) in self.re_export_paths.iter_mut() {
            for path in paths.iter() {
                let tbd_path = root_path.join(tbd_relative_path(path)?);
                let tbd_info = TbdMetadata::from_path(&tbd_path)?;

                if let Some(symbols) = tbd_info.symbols.get(target) {
                    extra_symbols
                        .entry(target.clone())
                        .or_default()
                        .extend(symbols.iter().cloned());
                }
            }
        }

        for (target, symbols) in extra_symbols {
            self.symbols.entry(target).or_default().extend(symbols);
        }

        Ok(())
    }
}

pub struct IndexedSdks {
    sdks: Vec<SimpleSdk>,
}

impl IndexedSdks {
    pub fn new(path: impl AsRef<Path>) -> Result<Self> {
        let path = path.as_ref();

        let sdks = SdkSearch::empty()
            .location(SdkSearchLocation::Sdks(path.to_path_buf()))
            .sorting(SdkSorting::VersionAscending)
            .search::<SimpleSdk>()
            .context("searching for SDKs")?;

        Ok(Self { sdks })
    }

    fn required_sdks(&self, minimum_version: Version) -> Result<Vec<&SimpleSdk>> {
        let mut res = vec![];

        for sdk in &self.sdks {
            if let Some(sdk_version) = sdk.version() {
                if let Ok(sdk_version) = sdk_version.semantic_version() {
                    let sdk_version = Version::from_str(sdk_version.as_str())?;

                    if sdk_version >= minimum_version {
                        res.push(sdk);
                    }
                }
            }
        }

        Ok(res)
    }

    pub fn validate_context(
        &self,
        context: &mut ValidationContext,
        minimum_sdk: semver::Version,
        triple: &str,
    ) -> Result<()> {
        let symbol_target = match triple {
            "aarch64-apple-darwin" => "arm64e-macos",
            "x86_64-apple-darwin" => "x86_64-macos",
            _ => {
                context.errors.push(format!(
                    "unknown target triple for Mach-O symbol analysis: {triple}"
                ));
                return Ok(());
            }
        };

        let sdks = self.required_sdks(minimum_sdk)?;
        if sdks.is_empty() {
            context
                .errors
                .push("failed to resolve Apple SDKs to test against (this is likely a bug)".into());
            return Ok(());
        }

        for (lib, symbols) in &context.macho_undefined_symbols_strong.libraries {
            // Filter out `@executable_path`.
            if lib.strip_prefix('/').is_some() {
                let tbd_relative_path = tbd_relative_path(lib)?;

                for sdk in &sdks {
                    // The 10.9 SDK doesn't have TBDs. So skip it for now.
                    if let Some(version) = sdk.version() {
                        if version == &SdkVersion::from("10.9") {
                            continue;
                        }
                    }

                    let tbd_path = sdk.path().join(&tbd_relative_path);

                    if tbd_path.exists() {
                        let mut tbd_info = TbdMetadata::from_path(&tbd_path)?;
                        tbd_info.expand_file_references(sdk.path())?;

                        let empty = BTreeSet::new();

                        let target_symbols = tbd_info.symbols.get(symbol_target).unwrap_or(&empty);

                        for (symbol, paths) in &symbols.symbols {
                            if !target_symbols.contains(symbol) {
                                for path in paths {
                                    context.errors.push(format!(
                                        "{} references symbol {}:{} which doesn't exist in SDK {}",
                                        path.display(),
                                        lib,
                                        symbol,
                                        sdk.path().display()
                                    ));
                                }
                            }
                        }
                    } else {
                        for path in symbols.all_paths() {
                            context.errors.push(format!(
                                "library {} does not exist in SDK {}; {} will likely fail to load",
                                lib,
                                sdk.version().unwrap_or(&SdkVersion::from("99.99")),
                                path.display()
                            ));
                        }
                    }
                }
            }
        }

        Ok(())
    }
}
