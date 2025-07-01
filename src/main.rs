// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.

mod github;
mod json;
mod macho;
mod release;
mod validation;

use {
    anyhow::{anyhow, Context, Result},
    clap::{value_parser, Arg, ArgAction, Command},
    std::{
        io::Read,
        path::{Path, PathBuf},
    },
};

pub fn open_distribution_archive(path: &Path) -> Result<tar::Archive<impl Read>> {
    let fh =
        std::fs::File::open(path).with_context(|| format!("unable to open {}", path.display()))?;

    let reader = std::io::BufReader::new(fh);
    let dctx = zstd::stream::Decoder::new(reader)?;

    Ok(tar::Archive::new(dctx))
}

fn main_impl() -> Result<()> {
    let app = Command::new("Python Build")
        .arg_required_else_help(true)
        .version("0.1")
        .author("Gregory Szorc <gregory.szorc@gmail.com>")
        .about("Perform tasks related to building Python distributions");
    let app = app.subcommand(
        Command::new("fetch-release-distributions")
            .about("Fetch builds from GitHub Actions that are release artifacts")
            .arg(
                Arg::new("token")
                    .long("token")
                    .action(ArgAction::Set)
                    .required(true)
                    .help("GitHub API token"),
            )
            .arg(
                Arg::new("commit")
                    .long("commit")
                    .action(ArgAction::Set)
                    .help("Git commit whose artifacts to fetch"),
            )
            .arg(
                Arg::new("dest")
                    .long("dest")
                    .required(true)
                    .action(ArgAction::Set)
                    .value_parser(value_parser!(PathBuf))
                    .help("Destination directory"),
            )
            .arg(
                Arg::new("organization")
                    .long("org")
                    .action(ArgAction::Set)
                    .default_value("astral-sh")
                    .help("GitHub organization"),
            )
            .arg(
                Arg::new("repo")
                    .long("repo")
                    .action(ArgAction::Set)
                    .default_value("python-build-standalone")
                    .help("GitHub repository name"),
            )
            .arg(
                Arg::new("github-uri")
                    .long("github-uri")
                    .action(ArgAction::Set)
                    .help("Alternative GitHub URI"),
            ),
    );

    let app = app.subcommand(
        Command::new("convert-install-only")
            .about("Convert a .tar.zst archive to an install_only tar.gz archive")
            .arg(
                Arg::new("path")
                    .required(true)
                    .action(ArgAction::Append)
                    .value_parser(value_parser!(PathBuf))
                    .help("Path of archive to convert"),
            ),
    );

    let app = app.subcommand(
        Command::new("convert-install-only-stripped")
            .about("Convert an install_only .tar.gz archive to an install_only_stripped tar.gz archive")
            .arg(
                Arg::new("path")
                    .required(true)
                    .action(ArgAction::Append)
                    .value_parser(value_parser!(PathBuf))
                    .help("Path of archive to convert"),
            ),
    );

    let app = app.subcommand(
        Command::new("upload-release-distributions")
            .about("Upload release distributions to a GitHub release")
            .arg(
                Arg::new("token")
                    .long("token")
                    .action(ArgAction::Set)
                    .required(true)
                    .help("GitHub API token"),
            )
            .arg(
                Arg::new("dist")
                    .long("dist")
                    .action(ArgAction::Set)
                    .required(true)
                    .value_parser(value_parser!(PathBuf))
                    .help("Directory with release artifacts"),
            )
            .arg(
                Arg::new("datetime")
                    .long("datetime")
                    .action(ArgAction::Set)
                    .required(true)
                    .help("Date/time tag associated with builds"),
            )
            .arg(
                Arg::new("dry_run")
                    .short('n')
                    .action(ArgAction::SetTrue)
                    .help("Dry run mode; do not actually upload"),
            )
            .arg(
                Arg::new("tag")
                    .long("tag")
                    .action(ArgAction::Set)
                    .required(true)
                    .help("Release tag"),
            )
            .arg(
                Arg::new("ignore_missing")
                    .long("ignore-missing")
                    .action(ArgAction::SetTrue)
                    .help("Continue even if there are missing artifacts"),
            )
            .arg(
                Arg::new("organization")
                    .long("org")
                    .action(ArgAction::Set)
                    .default_value("astral-sh")
                    .help("GitHub organization"),
            )
            .arg(
                Arg::new("repo")
                    .long("repo")
                    .action(ArgAction::Set)
                    .default_value("python-build-standalone")
                    .help("GitHub repository name"),
            )
            .arg(
                Arg::new("github-uri")
                    .long("github-uri")
                    .action(ArgAction::Set)
                    .help("Alternative GitHub URI"),
            ),
    );

    let app = app.subcommand(
        Command::new("validate-distribution")
            .about("Ensure a distribution archive conforms to standards")
            .arg(
                Arg::new("run")
                    .long("run")
                    .action(ArgAction::SetTrue)
                    .help("Run the interpreter to verify behavior"),
            )
            .arg(
                Arg::new("macos_sdks_path")
                    .long("macos-sdks-path")
                    .action(ArgAction::Set)
                    .help("Path to a directory containing MacOS SDKs (typically a checkout of https://github.com/phracker/MacOSX-SDKs)")
            )
            .arg(
                Arg::new("path")
                    .help("Path to tar.zst file to validate")
                    .action(ArgAction::Append)
                    .value_parser(value_parser!(PathBuf))
                    .required(true),
            ),
    );

    let matches = app.get_matches();

    match matches.subcommand() {
        Some(("convert-install-only", args)) => {
            for path in args.get_many::<PathBuf>("path").unwrap() {
                let dest_path = release::produce_install_only(path)?;
                println!("wrote {}", dest_path.display());
            }

            Ok(())
        }
        Some(("convert-install-only-stripped", args)) => {
            let llvm_dir = tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()
                .unwrap()
                .block_on(release::bootstrap_llvm())?;
            for path in args.get_many::<PathBuf>("path").unwrap() {
                let dest_path = release::produce_install_only_stripped(path, &llvm_dir)?;
                println!("wrote {}", dest_path.display());
            }

            Ok(())
        }
        Some(("fetch-release-distributions", args)) => {
            tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()
                .unwrap()
                .block_on(github::command_fetch_release_distributions(args))
        }
        Some(("upload-release-distributions", args)) => {
            tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()
                .unwrap()
                .block_on(github::command_upload_release_distributions(args))
        }
        Some(("validate-distribution", args)) => validation::command_validate_distribution(args),
        _ => Err(anyhow!("invalid sub-command")),
    }
}

fn main() {
    let exit_code = match main_impl() {
        Ok(()) => 0,
        Err(err) => {
            eprintln!("Error: {:?}", err);
            1
        }
    };

    std::process::exit(exit_code);
}
