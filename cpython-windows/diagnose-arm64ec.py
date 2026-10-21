import os
import pathlib
import shutil
import subprocess
import sys

executable = pathlib.Path(sys.argv[1])
output = executable.parent
destination = pathlib.Path("build/arm64ec-diagnostics")
original = destination / "original"
original.mkdir(parents=True, exist_ok=True)
for source in output.iterdir():
    if source.suffix.lower() in {".exe", ".dll", ".pyd"}:
        shutil.copy2(source, original / source.name)

tools = pathlib.Path(os.environ["VCToolsInstallDir"])
crt_directories = [original, None]
crt_directories.extend(
    sorted((tools.parents[2] / "Redist/MSVC").glob("*/arm64/Microsoft.VC*.CRT"))
)
pgo_runtimes = [original / "pgort140.dll"]
pgo_runtimes.extend(sorted(tools.rglob("pgort140.dll")))

env = dict(os.environ)
env["PYTHONHOME"] = str(executable.parents[3])
env.pop("PYTHONPATH", None)
for crt in crt_directories:
    for runtime in output.glob("vcruntime140*.dll"):
        runtime.unlink()
    if crt is not None:
        for runtime in crt.glob("vcruntime140*.dll"):
            shutil.copy2(runtime, output / runtime.name)
    for pgo in pgo_runtimes:
        shutil.copy2(pgo, output / "pgort140.dll")
        print(f"CRT={crt or 'system'} PGO={pgo}", flush=True)
        try:
            result = subprocess.run(
                [str(executable), "-c", "import sys; print(sys.version)"],
                env=env,
                capture_output=True,
                timeout=15,
            )
        except subprocess.TimeoutExpired:
            print("STARTUP TIMEOUT", flush=True)
            continue
        print(f"EXIT=0x{result.returncode & 0xFFFFFFFF:08X}", flush=True)
        print(result.stdout.decode("utf-8", "replace"), flush=True)
        print(result.stderr.decode("utf-8", "replace"), flush=True)

for source in original.glob("*.dll"):
    shutil.copy2(source, output / source.name)
