# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

param (
    [Parameter(Mandatory = $true)]
    [string[]]$Packages
)

# stop on executable failures
$PSNativeCommandUseErrorActionPreference = $true

# Available versions: https://cygwin.com/setup/
# Published SHA512 hashes: https://cygwin.com/setup/sha512.sum
$setupUrl = 'https://astral-sh.github.io/mirror/files/setup-2.939.x86_64.exe'
# Mirrored from:
#$setupUrl = 'https://cygwin.com/setup/setup-2.939.x86_64.exe'
$setupSha512 = 'e5a8ad58eeec0b3d9800e75783234ec6e788147d0f428aeeb8f7ad4a5f187e94b6a6f4b589f850266fb0a55d81e6d295a4a3cd2678accab5d062fc56216bf875'

$setup = Join-Path $env:RUNNER_TEMP 'setup.exe'
$root = 'C:\cygwin'

# Download and verify the installer
Invoke-WebRequest -Uri $setupUrl -OutFile $setup -TimeoutSec 60  -MaximumRetryCount 5
$hash = (Get-FileHash -LiteralPath $setup -Algorithm SHA512).Hash
if ($hash -ine $setupSha512) {
    throw "Cygwin installer checksum mismatch: expected $setupSha512, got $hash"
}

# Run the install
# Pipe output so PowerShell waits for the GUI installer to exit.
& $setup `
    --quiet-mode `
    --no-shortcuts `
    --only-site `
    --no-version-check `
    --root $root `
    --local-package-dir 'C:\cygwin-packages' `
    --site 'https://mirrors.kernel.org/sourceware/cygwin/' `
    --packages ($Packages -join ',') | Out-Default

# Initialize profile files
& "$root\bin\bash.exe" --login -c 'true'

# Add to path
"$root\bin" >> $env:GITHUB_PATH
