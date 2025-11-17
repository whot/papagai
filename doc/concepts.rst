Concepts
========

This page explains the core concepts and architecture of papagai.

Worktrees
---------

What are Worktrees?
~~~~~~~~~~~~~~~~~~~

Worktrees allow you to have multiple working directories for a single
repository. Papagai uses worktrees to isolate Claude's work from your main
development environment.

**Benefits:**

* Work on multiple tasks simultaneously without switching branches
* Keep your main workspace clean and unaffected by Claude's changes
* Easy rollback - just delete the worktree branch if you don't like the changes
* Safe experimentation without risking your working code

Isolation Modes
---------------

Papagai supports two isolation modes for running Claude: OverlayFS and git worktrees.
The default is to use OverlayFS if the ``fuse-overlayfs`` binary is found, otherwise normal
git worktrees are used. See the ``--isolation`` option on the various ``papagai`` commands.

We prefer OverlayFS because it separates he main git repo and protects it from
Claude potentially messing with other branches on the repository. Only the ``papagai``
branch is pulled back into the main repo, so were Claude to maliciously modify
the ``main`` branch those changes will be thrown away at the end of the task.
git worktrees cannot provide this protection.


How Papagai Uses Worktrees
~~~~~~~~~~~~~~~~~~~~~~~~~~~

When you run a papagai command:

1. Creates a new git worktree in a temporary directory

   - for OverlayFS this is in ``XDG_CACHE_HOME/papagai/<reponame>/<base-branch>```
   - for git worktree this is in ``$PWD/papagai/<base-branch>/```

2. Creates a new branch with the naming pattern: ``papagai/<prefix><base>-<date-time>-<uuid>``
3. Runs Claude in that isolated worktree
4. Commits changes to the worktree branch
5. Returns to your original workspace

   - for OverlayFS: pull the work branch back into the main repo

6. Removes the worktree directory (see the ``--keep`` option if you need to keep the tree)

The ``papagai/latest`` branch always points to the most recent work, making it easy to find.

Branch Naming
-------------

Branch Naming Convention
~~~~~~~~~~~~~~~~~~~~~~~~~

Papagai creates branches following a specific pattern:

.. code-block:: text

   papagai/<prefix><base-branch>-<YYYYmmdd-HHMM>-<uuid>

**Components:**

* ``papagai/`` - Namespace prefix for easy identification
* ``<prefix>`` - Optional prefix (e.g., ``review/`` for ``papagai review``)
* ``<base-branch>`` - The branch you were on when starting
* ``<YYYYmmdd-HHMM>`` - Timestamp when the branch was created
* ``<uuid>`` - Short unique identifier

**Examples:**

.. code-block:: text

   papagai/main-20251112-1030-7be3946e
   papagai/wip/develop-20251113-1445-abc123fe

The special branch ``papagai/latest`` always points to the most recently
completed papagai task. This makes it easy to find your latest work without
remembering the exact branch name.

Finding Your Work
~~~~~~~~~~~~~~~~~

List all papagai branches:

.. code-block:: console

   $ git branch --list 'papagai/*'
   papagai/latest
   papagai/main-20251112-1030-7be3946e
   papagai/main-20251113-1445-abc123fe

Check out the latest work:

.. code-block:: console

   $ git checkout papagai/latest
