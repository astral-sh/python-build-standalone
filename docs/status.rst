.. _status:

==============
Project Status
==============

There is support for producing CPython distributions for Windows,
macOS, Linux, and iOS. All distributions are highly self-contained and have
limited shared library dependencies.

Planned and features include:

* Static/dynamic linking toggles for dependencies
* Support for configuring which toolchain/version to use
* Support for BSDs
* Support for Android
* Support for Python distributions that aren't CPython

Target Notes
============

Non-Darwin Apple Targets
------------------------

Apple targets that aren't Darwin/macOS (iOS, tvOS, watchOS, and corresponding
simulators) are considered alpha quality. The builds may or may not work. The
builds haven't been widely tested.

Only Python 3.9 is currently supported.

Non-x86 Linux Targets
---------------------

Linux targets for non-x86 (not ``i686-*`` or ``x86_64-*``) are considered alpha
quality.

The Linux cross builds use a different build environment based on Debian
Stretch (as opposed to Debian Jessie) and they use the cross tools Debian
packages (as opposed to using a modern Clang built from source).

These builds haven't been widely tested. There are likely several rough
edges with them.

Only Python 3.9 is currently supported.

Test Failures
=============

This repository contains ``test-distribution.py`` script that can be
used to run the Python test harness from a distribution archive.

Here, we track the various known failures when running
``test-distribution.py /path/to/distribution.tar.zst -u all``.

``test__locale``
----------------

Known failing on: Windows

This test fails as follows::

    ======================================================================
    ERROR: test_float_parsing (test.test__locale._LocaleTests)
    ----------------------------------------------------------------------
    Traceback (most recent call last):
      File "C:\Users\gps\AppData\Local\Temp\tmpjx7a33kd\python\install\lib\test\test__locale.py", line 184, in test_float_parsing
        if localeconv()['decimal_point'] != '.':
    UnicodeDecodeError: 'locale' codec can't decode byte 0xa0 in position 0: decoding error

    ======================================================================
    ERROR: test_lc_numeric_localeconv (test.test__locale._LocaleTests)
    ----------------------------------------------------------------------
    Traceback (most recent call last):
      File "C:\Users\gps\AppData\Local\Temp\tmpjx7a33kd\python\install\lib\test\test__locale.py", line 130, in test_lc_numeric_localeconv
        formatting = localeconv()
    UnicodeDecodeError: 'locale' codec can't decode byte 0xa0 in position 0: decoding error

    ----------------------------------------------------------------------

``test_locale``
---------------

Known failing on: Windows

This test fails on Windows::

    ======================================================================
    ERROR: test_getsetlocale_issue1813 (test.test_locale.TestMiscellaneous)
    ----------------------------------------------------------------------
    Traceback (most recent call last):
      File "C:\Users\gps\AppData\Local\Temp\tmp8m94v2m5\python\install\lib\test\test_locale.py", line 567, in test_getsetlocale_issue1813
        locale.setlocale(locale.LC_CTYPE, loc)
      File "C:\Users\gps\AppData\Local\Temp\tmp8m94v2m5\python\install\lib\locale.py", line 608, in setlocale
        return _setlocale(category, locale)
    locale.Error: unsupported locale setting

    ----------------------------------------------------------------------

``test_subprocess``
-------------------

Known Failing on: Linux

This fails in the following manner::

    test_executable_without_cwd (test.test_subprocess.ProcessTestCaseNoPoll) ... Could not find platform independent libraries <prefix>
    Could not find platform dependent libraries <exec_prefix>
    Consider setting $PYTHONHOME to <prefix>[:<exec_prefix>]
    Fatal Python error: initfsencoding: Unable to get the locale encoding
    ModuleNotFoundError: No module named 'encodings'

    Current thread 0x00007fd77c231740 (most recent call first):
    FAIL

    ======================================================================
    FAIL: test_executable_without_cwd (test.test_subprocess.ProcessTestCaseNoPoll)
    ----------------------------------------------------------------------
    Traceback (most recent call last):
      File "/tmp/tmp8hef0kr4/python/install/lib/python3.7/test/test_subprocess.py", line 436, in test_executable_without_cwd
        executable=sys.executable)
      File "/tmp/tmp8hef0kr4/python/install/lib/python3.7/test/test_subprocess.py", line 355, in _assert_cwd
        self.assertEqual(47, p.returncode)
    AssertionError: 47 != -6

We're unsure what is going on here. The error from ``initfsencoding``
is what happens when the first ``import`` during ``Py_Initialize()``
fails. So it appears the test somehow can't locate the Python
standard library.

``test_tk``
-----------

Known Failing on: Linux

This fails in the following manner::

    ======================================================================
    FAIL: test_from (tkinter.test.test_tkinter.test_widgets.ScaleTest)
    ----------------------------------------------------------------------
    Traceback (most recent call last):
      File "/tmp/tmpoqqjd5gi/python/install/lib/python3.7/tkinter/test/test_tkinter/test_widgets.py", line 867, in test_from
        self.checkFloatParam(widget, 'from', 100, 14.9, 15.1, conv=float_round)
      File "/tmp/tmpoqqjd5gi/python/install/lib/python3.7/tkinter/test/widget_tests.py", line 106, in checkFloatParam
        self.checkParam(widget, name, value, conv=conv, **kwargs)
      File "/tmp/tmpoqqjd5gi/python/install/lib/python3.7/tkinter/test/widget_tests.py", line 63, in checkParam
        self.assertEqual2(widget[name], expected, eq=eq)
      File "/tmp/tmpoqqjd5gi/python/install/lib/python3.7/tkinter/test/widget_tests.py", line 47, in assertEqual2
        self.assertEqual(actual, expected, msg)
    AssertionError: 14.9 != 15.0

This seems like a minor issue and might be a bug in the test itself.

``test_winconsoleio``
---------------------

This fails as follows::

    ======================================================================
    ERROR: test_ctrl_z (test.test_winconsoleio.WindowsConsoleIOTests)
    ----------------------------------------------------------------------
    Traceback (most recent call last):
      File "C:\Users\gps\AppData\Local\Temp\tmp8m94v2m5\python\install\lib\test\test_winconsoleio.py", line 190, in test_ctrl_z
        a, b = stdin.read(1), stdin.readall()
    OSError: [WinError 87] The parameter is incorrect

    ======================================================================
    ERROR: test_input (test.test_winconsoleio.WindowsConsoleIOTests)
    ----------------------------------------------------------------------
    Traceback (most recent call last):
      File "C:\Users\gps\AppData\Local\Temp\tmp8m94v2m5\python\install\lib\test\test_winconsoleio.py", line 144, in test_input
        self.assertStdinRoundTrip('abc123')
      File "C:\Users\gps\AppData\Local\Temp\tmp8m94v2m5\python\install\lib\test\test_winconsoleio.py", line 137, in assertStdinRoundTrip
        actual = input()
    OSError: [WinError 87] The parameter is incorrect

    ======================================================================
    FAIL: test_partial_reads (test.test_winconsoleio.WindowsConsoleIOTests)
    ----------------------------------------------------------------------
    Traceback (most recent call last):
      File "C:\Users\gps\AppData\Local\Temp\tmp8m94v2m5\python\install\lib\test\test_winconsoleio.py", line 166, in test_partial_reads
        self.assertEqual(actual, expected, 'stdin.read({})'.format(read_count))
    AssertionError: b'\r\n' != b'\xcf\xbc\xd1\x9e\xd0\xa2\xce\xbb\xd0\xa4\xd0\x99\r\n' : stdin.read(1)

    ======================================================================
    FAIL: test_partial_surrogate_reads (test.test_winconsoleio.WindowsConsoleIOTests)
    ----------------------------------------------------------------------
    Traceback (most recent call last):
      File "C:\Users\gps\AppData\Local\Temp\tmp8m94v2m5\python\install\lib\test\test_winconsoleio.py", line 183, in test_partial_surrogate_reads
        self.assertEqual(actual, expected, 'stdin.read({})'.format(read_count))
    AssertionError: b'\xc3\x84\r\n' != b'\xf4\x81\xbf\xbf\xf4\x81\x80\x81\r\n' : stdin.read(1)

    ----------------------------------------------------------------------

    Ran 10 tests in 0.006s

    FAILED (failures=2, errors=2)
    test test_winconsoleio failed
    0:00:00 Re-running test__locale in verbose mode
    test_float_parsing (test.test__locale._LocaleTests) ... ERROR
    test_lc_numeric_basic (test.test__locale._LocaleTests) ... skipped 'nl_langinfo is not available'
    test_lc_numeric_localeconv (test.test__locale._LocaleTests) ... ERROR
    test_lc_numeric_nl_langinfo (test.test__locale._LocaleTests) ... skipped 'nl_langinfo is not available'

    ======================================================================
    ERROR: test_float_parsing (test.test__locale._LocaleTests)
    ----------------------------------------------------------------------
    Traceback (most recent call last):
      File "C:\Users\gps\AppData\Local\Temp\tmp8m94v2m5\python\install\lib\test\test__locale.py", line 184, in test_float_parsing
        if localeconv()['decimal_point'] != '.':
    UnicodeDecodeError: 'locale' codec can't decode byte 0xa0 in position 0: decoding error

    ======================================================================
    ERROR: test_lc_numeric_localeconv (test.test__locale._LocaleTests)
    ----------------------------------------------------------------------
    Traceback (most recent call last):
      File "C:\Users\gps\AppData\Local\Temp\tmp8m94v2m5\python\install\lib\test\test__locale.py", line 130, in test_lc_numeric_localeconv
        formatting = localeconv()
    UnicodeDecodeError: 'locale' codec can't decode byte 0xa0 in position 0: decoding error

    ----------------------------------------------------------------------


Test Skips
==========

Linux
-----

The following tests are skipped on Linux:

test_asdl_parser
   test irrelevant for an installed Python
test_clinic
   install/lib/Tools/clinic' path does not exist
test_dbm_gnu
   No module named '_gdbm'
test_devpoll
   test works only on Solaris OS family
test_gdb
   test_gdb only works on source builds at the moment.
test_kqueue
   test works only on BSD
test_msilib
   No module named 'msilib'
test_ossaudiodev
   [Errno 2] No such file or directory: '/dev/dsp'
test_startfile
   object <module 'os' from '.../install/lib/python3.7/os.py'> has no attribute 'startfile'
test_winconsoleio
   test only relevant on win32
test_winreg
   No module named 'winreg'
test_winsound
   No module named 'winsound'
test_zipfile64
   test requires loads of disk-space bytes and a long time to run

macOS
-----

The following tests are skipped on macOS:

test_asdl_parser
   test irrelevant for an installed Python
test_clinic
   python/install/lib/Tools/clinic' path does not exist
test_dbm_gnu
   No module named '_gdbm'
test_devpoll
   test works only on Solaris OS family
test_epoll
   test works only on Linux 2.6
test_gdb
   Couldn't find gdb on the path
test_msilib
   No module named 'msilib'
test_multiprocessing_fork
   test may crash on macOS (bpo-33725)
test_nis
   No module named 'nis'
test_ossaudiodev
   No module named 'ossaudiodev'
test_spwd
   No module named 'spwd'
test_startfile
   object <module 'os' from '.../install/lib/python3.7/os.py'> has no attribute 'startfile'
test_tix
   tix is not built by this project
test_tk
   cannot run without OS X gui process
test_ttk_guionly
   cannot run without OS X gui process
test_winconsoleio
   test only relevant on win32
test_winreg
   No module named 'winreg'
test_winsound
   No module named 'winsound'
test_zipfile64
   test requires loads of disk-space bytes and a long time to run
