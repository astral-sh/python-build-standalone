Python Standalone Builds
========================

This project produces self-contained, highly portable, high-performance
Python distributions. These Python distributions contain a fully usable,
full-featured Python installation: most extension modules from the Python
standard library are present, and their library dependencies are either
distributed with the distribution or are statically linked.

The Python distributions are built in a manner to minimize
run-time dependencies. This includes limiting the CPU instructions
that can be used and limiting the set of shared libraries required
at run-time. The goal is for the produced distribution to work on
any system for the targeted architecture.

The builds incorporate compiler optimizations such as profile-guided
optimization (PGO), link-time optimization (LTO), and, where appropriate,
BOLT post-link binary optimization. Together, these techniques improve
runtime performance while preserving portability.

The most common method of using these distributions is with
`uv <https://docs.astral.sh/uv/>`_.

To run a particular distribution using ``uv``::

    uvx --managed-python python

A Python version or another specifier can be included::

    uvx --managed-python python@3.13
    uvx --managed-python python@3.14+freethreaded

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   running
   building
   quirks
   technotes
   distributions
   status

Indices and tables
==================

* :ref:`genindex`
* :ref:`search`
