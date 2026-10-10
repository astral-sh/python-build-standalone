# LLVM distribution builds

Build and package LLVM 23.1.1 (Clang, lld, BOLT, and compiler runtimes) for
python-build-standalone on Linux x86-64/AArch64 or Apple Silicon macOS.
Archives are written to `toolchain/build/`, each containing an `llvm/` directory.

For Linux artifacts, use Docker with Buildx on a matching native builder.

x86_64:

```sh
cd toolchain
./build-linux-x86_64.sh
```

aarch64:

```sh
cd toolchain
./build-linux-aarch64.sh
```

On Apple Silicon macOS, use `uv` and Xcode Command Line Tools:

```sh
cd toolchain
./build-macos.py
```
