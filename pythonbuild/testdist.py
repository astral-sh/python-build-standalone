# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import argparse
import concurrent.futures
import dataclasses
import enum
import json
import os
import re
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from junitparser import JUnitXml

from .cpython import (
    TEST_ANNOTATION_HARNESS_SKIP,
    TEST_ANNOTATION_MODULE_EXCLUDE,
    TEST_ANNOTATION_PROFILING_EXCLUDE,
    TEST_ANNOTATION_PROFILING_SKIP,
    TEST_ANNOTATION_TEST_FAILURE,
    TestAnnotation,
    meets_python_minimum_version,
)
from .utils import extract_python_archive

# Tests in the standard library that are slow.
#
# Roughly in order from slowest to fastest.
STDLIB_SLOW_TESTS = [
    "test_subprocess",
    "test_signal",
    "test_socket",
    "test.test_multiprocessing_spawn.test_processes",
    "test.test_multiprocessing_forkserver.test_processes",
    "test_regrtest",
    "test.test_concurrent_futures.test_process_pool",
    "test_tarfile",
    "test_socket",
    "test_remote_pdb",
    "test_threading",
    "test.test_concurrent_futures.test_as_completed",
    "test.test_multiprocessing_spawn.test_misc",
    "test.test_asyncio.test_tasks",
    "test_zipfile",
    "test_pickle",
]

# Maximum wall run time of a single test before timing it out.
TIMEOUT_SECONDS = 300


def run_dist_python(
    dist_root: Path,
    python_info,
    args: list[str],
    extra_env: Optional[dict[str, str]] = None,
    log_exec=False,
    **runargs,
) -> subprocess.CompletedProcess[bytes]:
    """Runs a `python` process from an extracted PBS distribution.

    This function attempts to isolate the spawned interpreter from any
    external interference (PYTHON* environment variables), etc.
    """
    env = dict(os.environ)

    # Wipe PYTHON environment variables.
    for k in env:
        if k.startswith("PYTHON"):
            del env[k]

    if extra_env:
        env.update(extra_env)

    all_args = [str(dist_root / python_info["python_exe"])] + args

    if log_exec:
        print(f"executing: {shlex.join(all_args)}")

    return subprocess.run(
        all_args,
        cwd=dist_root,
        env=env,
        **runargs,
    )


def run_custom_unittests(pbs_source_dir: Path, dist_root: Path, python_info) -> int:
    """Runs custom PBS unittests against a distribution."""

    args = [
        "-m",
        "unittest",
        "pythonbuild.disttests",
    ]

    env = {
        "PYTHONPATH": str(pbs_source_dir),
        "TARGET_TRIPLE": python_info["target_triple"],
        "BUILD_OPTIONS": python_info["build_options"],
    }

    res = run_dist_python(dist_root, python_info, args, env, stderr=subprocess.STDOUT)

    return res.returncode


def run_stdlib_tests(
    dist_root: Path,
    python_info,
    skip_main=False,
    verbose_expected_failures=False,
    raw_harness_args: Optional[list[str]] = None,
) -> tuple[int, JUnitXml]:
    """Run Python stdlib tests for a PBS distribution.

    The passed path is the `python` directory from the extracted distribution
    archive.
    """

    dist_name = f"cpython-{python_info['python_version']}-{python_info['build_options']}-{python_info['target_triple']}"

    stdlib_test_annotations_path = dist_root / "build" / "stdlib-test-annotations.json"

    with stdlib_test_annotations_path.open("r", encoding="utf-8") as fh:
        annotations = json.load(fh)

    expect_failures = set()
    module_excludes = set()
    intermittent = set()
    dont_verify = set()

    for raw_annotation in annotations:
        annotation = TestAnnotation(**raw_annotation)

        name = annotation.name
        flavor = annotation.flavor
        reason = annotation.reason

        if flavor == TEST_ANNOTATION_HARNESS_SKIP:
            print(f"not running the stdlib test harness: {reason}")

            # Add a GitHub Actions annotation to improve observability of this scenario.

            if "CI" in os.environ:
                print(
                    f"::notice title={dist_name} stdlib test harness skipped::{reason}"
                )

            return 0, JUnitXml()

        elif flavor == TEST_ANNOTATION_MODULE_EXCLUDE:
            print(f"excluding module {name}: {reason}")
            module_excludes.add(name)
            continue

        elif flavor == TEST_ANNOTATION_TEST_FAILURE:
            print(f"expected test failure {name}: {reason}")
            expect_failures.add(name)

            if annotation.intermittent_test_failure:
                intermittent.add(name)
            if annotation.dont_verify:
                dont_verify.add(name)

        elif flavor == TEST_ANNOTATION_PROFILING_EXCLUDE:
            print(f"profiling exclude module ignored {name}")
            continue

        elif flavor == TEST_ANNOTATION_PROFILING_SKIP:
            print(f"profiling skip test ignored {name}")
            continue

        else:
            raise Exception(f"unhandled test annotation flavor: {flavor}")

    base_args = [
        "-u",
        "-W",
        "default",
        "-bb",
        "-E",
        "-m",
        "test",
    ]

    args = list(base_args)

    td = tempfile.TemporaryDirectory()
    junit_path = Path(td.name) / "junit.xml"

    if raw_harness_args:
        args.extend(raw_harness_args)
    else:
        args.extend(
            [
                # Display test output on failure. Makes it easier to debug failures.
                "-W",
                # Re-run failed tests in verbose mode to aid debugging.
                "-w",
                # Make order non-deterministic to help flush out failures.
                "--randomize",
                # Run tests in parallel using all available CPUs.
                "-j",
                "0",
                # Force abort tests taking too long to execute. This can prevent
                # some runaway tests in CI.
                "--timeout",
                str(TIMEOUT_SECONDS),
                # Print slowest tests to make it easier to audit our slow tests list.
                "-o",
                # Write test results to a junit XML file.
                "--junit-xml",
                str(junit_path),
            ]
        )

        # 3.14 added a test harness feature to prioritize running tests. Prioritize
        # running slow tests first to mitigate long poles slowing down harness execution.
        if meets_python_minimum_version(python_info["python_version"], "3.14"):
            args.extend(["--prioritize", ",".join(STDLIB_SLOW_TESTS)])

        for test_name in sorted(expect_failures):
            args.extend(["--ignore", test_name])

        if module_excludes:
            # --exclude is a boolean argument that changes positional arguments to
            # denotes excludes. As of at least 3.15 there doesn't appear to be a
            # way to select tests to run via positional arguments while also
            # excluding certain modules from being loaded.
            args.append("--exclude")
            args.extend(sorted(module_excludes))

    codes = []

    if not skip_main:
        codes.append(
            run_dist_python(dist_root, python_info, args, log_exec=True).returncode
        )
        if codes[-1] != 0:
            print(f"main test harness failed ({codes[-1]})")
        else:
            print("main test harness passed")
    else:
        print("main test harness skipped")

    try:
        junit = JUnitXml.fromfile(str(junit_path))
    except FileNotFoundError:
        junit = JUnitXml()

    if not raw_harness_args:
        for result in _run_stdlib_expected_failures(
            dist_root,
            python_info,
            base_args,
            expect_failures,
            intermittent,
            dont_verify,
            verbose_expected_failures=verbose_expected_failures,
        ):
            if result.unexpected:
                codes.append(1)
            else:
                codes.append(0)

            # Concatenate all the junit test suites together.
            if result.junit is not None:
                junit += result.junit

    if any(code != 0 for code in codes):
        return 1, junit
    else:
        return 0, junit


class TestResultReason(enum.StrEnum):
    NONE = ""
    EXPECTED = "expected"
    UNKNOWN_TEST = "unknown test"
    INTERMITTENT_PASS_ALLOWED = "intermittent pass allowed"
    DONT_VERIFY_PASS_ALLOWED = "dont-verify annotation allows pass"
    DONT_VERIFY_FAIL_ALLOWED = "dont-verify annotation allows fail"
    UNEXPECTED_PASS = "unexpected pass"


@dataclasses.dataclass
class ExpectedFailureResult:
    test_name: str
    code: int
    output: bytes
    fails: bool
    result_reason: TestResultReason
    unexpected: bool
    intermittent: bool
    dont_verify: bool
    junit: Optional[JUnitXml]


def _run_stdlib_expected_failures(
    dist_root: Path,
    python_info,
    base_args: list[str],
    expect_failures: set[str],
    intermittent: set[str],
    dont_verify: set[str],
    verbose_expected_failures: bool,
) -> list[ExpectedFailureResult]:
    results = []
    unexpected_tests: set[str] = set()

    with concurrent.futures.ThreadPoolExecutor() as executor:
        fs = []

        for test_name in sorted(expect_failures):
            fs.append(
                executor.submit(
                    _check_stdlib_expected_failure,
                    dist_root,
                    python_info,
                    base_args,
                    test_name,
                    test_name in intermittent,
                    test_name in dont_verify,
                )
            )

        for i, f in enumerate(concurrent.futures.as_completed(fs)):
            res: ExpectedFailureResult = f.result()

            results.append(res)

            if res.unexpected:
                unexpected_tests.add(res.test_name)

            unexpected_suffix = ""
            if len(unexpected_tests) > 0:
                unexpected_suffix = f"/{len(unexpected_tests)}"

            fail_result = "yes" if res.fails else "no"

            if res.result_reason != TestResultReason.NONE:
                fail_result += f" ({res.result_reason})"

            print(
                f"[{i + 1}/{len(expect_failures)}{unexpected_suffix}] verifying {res.test_name} fails... {fail_result}"
            )

            print_output = verbose_expected_failures or res.result_reason in (
                TestResultReason.DONT_VERIFY_FAIL_ALLOWED,
                TestResultReason.UNKNOWN_TEST,
            )

            if print_output:
                for line in res.output.decode("utf-8", errors="ignore").splitlines():
                    print(f"> {line}")

    if unexpected_tests:
        print("unexpected test results:")
        for t in sorted(unexpected_tests):
            print(t)

    return results


RE_TEST_RUN_COUNT = re.compile(rb"^Total tests: run=(\d+)", re.MULTILINE)

RE_TEST_CRASHED = re.compile(rb"^test test_.+ crashed", re.MULTILINE)

RE_TEST_UNCAUGHT_EXCEPTION = re.compile(
    rb"test_.+ failed \(uncaught exception\)", re.MULTILINE
)

RE_TEST_SKIPPED = re.compile(rb"^test_.+ skipped", re.MULTILINE)


def _check_stdlib_expected_failure(
    dist_root: Path,
    python_info,
    base_args: list[str],
    test_name: str,
    intermittent: bool,
    dont_verify: bool,
) -> ExpectedFailureResult:
    args = list(base_args)

    args.extend(
        [
            "-v",
            "--timeout",
            str(TIMEOUT_SECONDS),
        ]
    )

    # Always provide the test_* name as a positional argument to limit
    # which tests are loaded. Otherwise we load all test files and incur
    # substantial overhead.

    parts = test_name.split(".")

    # time.datetimetester is loaded by test_datetime. This pattern was removed
    # in 3.11.
    if test_name.startswith("test.datetimetester."):
        module_name = "test_datetime"

    # distutils.tests is loaded by test_distutils. This pattern was removed
    # in 3.12.
    elif test_name.startswith("distutils.tests."):
        module_name = "test_distutils"

    elif test_name.startswith("test."):
        module_name = parts[1]

    else:
        raise ValueError(f"unknown test module pattern: {test_name}")

    args.extend(["-m", test_name])

    with tempfile.TemporaryDirectory() as td:
        junit_path = Path(td) / "junit.xml"
        args.extend(["--junit-xml", str(junit_path)])

        args.append(module_name)

        # We sniff stdout for certain string patterns. Non-deterministic color
        # sequences undermines those efforts. So prevent the test harness from
        # emitting colors.
        extra_env = {
            "NO_COLOR": "1",
        }

        res = run_dist_python(
            dist_root, python_info, args, extra_env=extra_env, capture_output=True
        )

        try:
            junit = JUnitXml.fromfile(str(junit_path))
        except FileNotFoundError:
            junit = None

    unexpected = False
    fails = False
    result_reason = None

    # Since we're running 1 test at a time, the test harness should always
    # run at least 1 test. If no tests are executed, it means we have a test
    # annotation referencing an unknown test. i.e. the test annotation is wrong
    # (likely incorrect minimum/maximum Python versions). Treat this as a hard
    # error to force our test annotations track reality.
    #
    # But this condition can also materialize if there's an error setting up
    # tests, including importing them. Said errors take precedence. Ditto for
    # if the load of the module itself self-skips.
    crashed = RE_TEST_CRASHED.search(res.stdout) is not None
    uncaught_exception = RE_TEST_UNCAUGHT_EXCEPTION.search(res.stdout) is not None
    load_error = b"\nERROR: setUpClass" in res.stdout
    skipped = RE_TEST_SKIPPED.search(res.stdout) is not None

    if not crashed and not uncaught_exception and not load_error and not skipped:
        # 3.13+ syntax.
        if m := RE_TEST_RUN_COUNT.search(res.stdout):
            if m.group(1) == b"0":
                fails = False
                result_reason = TestResultReason.UNKNOWN_TEST
                unexpected = True

        # 3.11-3.12 syntax.
        elif b"NO TESTS RAN" in res.stdout:
            fails = False
            result_reason = TestResultReason.UNKNOWN_TEST
            unexpected = True

        # 3.10 syntax.
        elif b"NO TEST RUN" in res.stdout:
            fails = False
            result_reason = TestResultReason.UNKNOWN_TEST
            unexpected = True

    if result_reason is None:
        if res.returncode != 0:
            fails = True
            result_reason = (
                TestResultReason.DONT_VERIFY_FAIL_ALLOWED
                if dont_verify
                else TestResultReason.EXPECTED
            )
        elif intermittent:
            fails = False
            result_reason = TestResultReason.INTERMITTENT_PASS_ALLOWED
        elif dont_verify:
            fails = False
            result_reason = TestResultReason.DONT_VERIFY_PASS_ALLOWED
        else:
            fails = False
            result_reason = TestResultReason.UNEXPECTED_PASS
            unexpected = True

    return ExpectedFailureResult(
        test_name,
        res.returncode,
        res.stdout,
        fails,
        result_reason,
        unexpected,
        intermittent,
        dont_verify,
        junit=junit,
    )


def main(pbs_source_dir: Path, raw_args: list[str]) -> int:
    """test-distribution.py functionality."""

    parser = argparse.ArgumentParser(
        description="""
        Runs unit tests against a Python distribution.
        
        By default, this executes custom PBS unit tests. The unittests from
        the distribution's Python standard library can be ran by adding --stdlib.
        
        By default, the stdlib test harness is run with opinionated behavior
        where we automatically exclude running tests annotated as failing followed
        by running each of these annotated tests in isolation to validate their
        test annotations. e.g. we validate that failures actually fail.
        
        If arguments are passed after a `--` separator argument, the execution
        behavior changes to a proxy to the stdlib test harness and arguments passed
        after `--` are passed directly to `python -m test`, allowing you to invoke
        the stdlib test harness with arbitrary arguments.
        
        The --stdlib-no-main (implies --stdlib) can be used to just run annotated
        test failures. This can be useful for debugging these tests.
        """
    )

    parser.add_argument(
        "--junit-xml",
        type=Path,
        help="Write test results to a JUnit XML file at the specified path",
    )
    parser.add_argument(
        "--stdlib",
        action="store_true",
        help="Run the stdlib test harness",
    )
    parser.add_argument(
        "--stdlib-no-main",
        action="store_true",
        help="Skip running the main invocation of the stdlib test harness - only failures will be processed",
    )
    parser.add_argument(
        "--verbose-expected-failures",
        action="store_true",
        help="Print details of tests that failed expectedly (helps with debugging failures)",
    )
    parser.add_argument(
        "dist",
        nargs=1,
        help="Path to distribution to test",
    )
    parser.add_argument(
        "stdlib_harness_args",
        nargs=argparse.REMAINDER,
        help="Raw arguments to pass to the stdlib test harness",
    )

    args = parser.parse_args(raw_args)

    if args.stdlib_no_main:
        args.stdlib = True

    dist_path_raw = Path(args.dist[0])

    td = None
    try:
        if dist_path_raw.is_file():
            td = tempfile.TemporaryDirectory()
            dist_path = extract_python_archive(dist_path_raw, Path(td.name))
        else:
            dist_path = dist_path_raw

        python_json = dist_path / "PYTHON.json"

        with python_json.open("r", encoding="utf-8") as fh:
            python_info = json.load(fh)

        codes = []
        junit = JUnitXml()

        # TODO support junit capture
        codes.append(run_custom_unittests(pbs_source_dir, dist_path, python_info))

        if args.stdlib or args.stdlib_harness_args:
            code, junit_stdlib = run_stdlib_tests(
                dist_path,
                python_info,
                skip_main=args.stdlib_no_main,
                verbose_expected_failures=args.verbose_expected_failures,
                raw_harness_args=args.stdlib_harness_args,
            )
            codes.append(code)
            junit += junit_stdlib

        junit_xml_path: Optional[Path] = args.junit_xml
        if junit_xml_path is not None:
            junit_xml_path.parent.mkdir(parents=True, exist_ok=True)
            with junit_xml_path.open("w", encoding="utf-8") as fh:
                junit.write(fh, pretty=True)

        if len(codes) == 0:
            print("no tests run")
            return 1

        if any(code != 0 for code in codes):
            return 1

        return 0

    finally:
        if td:
            td.cleanup()
