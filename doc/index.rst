papagai Documentation
=====================

``papagai`` is a command-line tool that runs Claude AI on git repositories
using isolated worktrees. It allows Claude to make changes without interfering
with the main working directory.

.. note:: ``papagai`` requires that the ``claude`` command is installed and set up.

The main goal of ``papagai`` is to make it trivial to invoke Claude for **local**
review and development. When Claude has finished, ``papagai`` merges the work back
into a ``papagai/<branch>-<date>-<time>-<uuid>`` branch and updates the
``papagai/latest`` branch to point at that branch.

Code review or development is thus a cycle of running ``papagai`` and cherry-picking
or merging from the ``papagai/latest`` branch.

Quick Start
-----------

Installation
~~~~~~~~~~~~

.. code-block:: console

   $ pip install papagai

Or directly install from git

.. code-block:: console

   $ pip install git+https://github.com/whot/papagai

Code review with papagai
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: console

   $ git switch  mybranch
   $ papagai review
   Working in papagai/review/mybranch-2025-11-12-7be3946e (based off main) or papagai/latest
   [...]
   My work here is done. Check out branch papagai/review/mybranch-2025-11-12-7be3946e or papagai/latest

The ``code`` command includes programming best practices guidance, while ``do`` runs without the programming primer.

Development with papagai
~~~~~~~~~~~~~~~~~~~~~~~~

The primary commands are ``code`` and ``do`` to get Claude to perform tasks:

.. code-block:: console

   $ papagai code
   Please tell me what you want me to do (Ctrl+D to complete)
   Update all .format() strings with f-strings
   Working in papagai/main-2025-11-12-7be3946e (based off main)
   [...]
   My work here is done. Check out branch papagai/main-2025-11-12-7be3946e

or, for more complex instructions, use a prewritten file:

.. code-block:: console

   $ papagai code instructions.md
   Working in papagai/main-2025-11-12-7be3946e (based off main)
   [...]
   My work here is done. Check out branch papagai/main-2025-11-12-7be3946e or papagai/latest

The ``code`` command includes programming best practices guidance, while ``do`` runs without the programming primer.

Documentation Contents
----------------------

.. toctree::
   :maxdepth: 2
   :caption: User Guide

   installation
   commands
   concepts

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
