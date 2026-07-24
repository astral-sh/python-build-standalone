## python-build-standalone performance

<img 
    width="1820" height="1730" 
    alt="Shows a chart with violin plots with benchmark results" 
    src="https://github.com/user-attachments/assets/5499f9ce-ee02-4485-baa2-9d982fe457e6"
/>

python-build-standalone provides high-performance CPython distributions designed for compatibility across a broad range of Linux distributions, macOS releases, and Windows versions. It's builds incorporate compiler optimizations such as profile-guided optimization (PGO), link-time optimization (LTO), and, where appropriate, BOLT post-link binary optimization. Together, these techniques improve runtime performance while preserving portability.
Benchmarks using the pyperformance suite show that python-build-standalone performs competitively with, and frequently outperforms, other widely used CPython distributions.


### Figure details

The figure above compares CPython 3.14.6 performance across several distributions using pyperformance. Each violin represents the distribution of per-benchmark mean runtime ratios between an alternative CPython distribution and python-build-standalone on the same platform and architecture. Ratios greater than 1 indicate that python-build-standalone was faster; ratios less than 1 indicate that the alternative distribution was faster.

The horizontal axis uses a logarithmic scale. The vertical marker within each violin indicates the geometric mean of the runtime ratios, which is also expressed as a percentage beside each distribution.

From top to bottom, the distributions shown are:
* The Docker `python:3.14` image for x86-64, providing CPython 3.14.6.
* A conda-forge Python 3.14.6 environment for `linux-64`.
* The system Python 3.14.6 in a `fedora:44` x86-64 Docker container.
* The system Python 3.14.6 in a debian:forky x86-64 Docker container.
* CPython 3.14.6 from the Python.org macOS installer on an arm64 Mac.
* A conda-forge Python 3.14.6 environment for `osx-arm64`.
* CPython 3.14.6 installed through Homebrew on an arm64 Mac.
* CPython 3.14.6 from the Python.org Windows installer for x86-64.
* A conda-forge Python 3.14.6 environment for `win-64`.

The reference interpreter for each comparison was the corresponding platform- and architecture-matched python-build-standalone CPython 3.14.6 distribution from the [`20260623` release](https://github.com/astral-sh/python-build-standalone/releases#release-20260623), installed using `uv`.

Benchmarks were run in early to mid-July 2026 and reflect the distributions and packages available during that period.

### Benchmark methodology

Benchmarks were executed from a virtual environment created with the reference interpreter into which pyperformance 1.14.0 was installed. Results were collected using:
``` shell
pyperformance run --rigorous --warmups 2 --output <logfile>
```

The complete benchmark suite was run at least twice to assess consistency.

Linux benchmarks were run inside Docker containers on an Ubuntu 24.04 host with an Intel Core i9-9900K processor. Hyper-Threading and Intel SpeedStep were disabled.

macOS benchmarks were run on a MacBook Pro with an Apple M5 Max processor.

Windows benchmarks were run on a Windows 11 host with an Intel Core i5-9500 processor. Intel Turbo Boost was disabled; this processor does not support Hyper-Threading.
