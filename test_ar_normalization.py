#!/usr/bin/env python3
"""Test that AR normalization works correctly."""
import os

def test_ar_normalization():
    """Simulate the string replacement to verify it works."""
    # Simulated sysconfig data
    test_cases = [
        # (input, expected_output, description)
        ("AR = /tools/llvm/bin/llvm-ar", "AR = llvm-ar", "Basic AR case"),
        ("RANLIB = /tools/llvm/bin/llvm-ranlib", "RANLIB = llvm-ranlib", "RANLIB case"),
        ("CC = /tools/llvm/bin/clang -pthread", "CC = clang -pthread", "CC with flags"),
        ("CXX = /tools/llvm/bin/clang++ -pthread", "CXX = clang++ -pthread", "CXX with flags"),
        # Edge cases
        ("PATH=/tools/llvm/bin:/usr/bin", "PATH=/tools/llvm/bin:/usr/bin", "PATH unchanged (no trailing /)"),
        ("Some random text", "Some random text", "No match - unchanged"),
        # Path normalization: our search pattern is normalized, so double-slash
        # in sysconfig data won't match (but that's OK - sysconfig should be normalized)
        ("AR = /tools//llvm/bin/llvm-ar", "AR = /tools//llvm/bin/llvm-ar", "Double slash in data won't match (expected)"),
        # Empty value after replacement (edge case)
        ("AR = /tools/llvm/bin/", "AR = ", "Trailing slash creates empty value (acceptable)"),
    ]

    tools_path = "/tools"
    toolchain = "llvm"

    # Use os.path.normpath to handle edge cases like double slashes
    toolchain_bin = os.path.normpath(os.path.join(tools_path, toolchain, "bin"))
    search = toolchain_bin + "/"
    replace = ""

    print(f"Testing replacement: '{search}' -> '{replace}'")
    print("-" * 60)

    all_passed = True
    for input_str, expected, description in test_cases:
        output = input_str.replace(search, replace)
        passed = output == expected
        status = "✓" if passed else "✗"

        print(f"{status} {description}")
        if not passed:
            print(f"  Input:    {input_str}")
            print(f"  Expected: {expected}")
            print(f"  Got:      {output}")
            all_passed = False

    print("-" * 60)
    if all_passed:
        print("All tests passed!")
        return 0
    else:
        print("Some tests failed!")
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(test_ar_normalization())
