Installation
============

Requirements
------------

* Python 3.10 or later
* git
* Optional: ``fuse-overlayfs`` for overlay filesystem worktree isolation
* Optional: the ``rich`` package for better logging (``pip install rich``)

Installing from Source
----------------------

Install directly from GitHub using pip:

.. code-block:: console

   $ pip install git+https://github.com/whot/papagai

Development Installation
------------------------

For development, clone the repository and use `uv <https://github.com/astral-sh/uv>`_:

.. code-block:: console

   $ git clone https://github.com/whot/papagai
   $ cd papagai
   $ uv run papagai --help


Verifying Installation
----------------------

After installation, verify that papagai is working:

.. code-block:: console

   $ papagai --help

You should see the help message with available commands.
