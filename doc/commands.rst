Commands
========

This page describes all available papagai commands. The options listed for
each command are the ones users are likely to user. Use the ``--help`` output
to see all options.

Any work by ``papagai`` will end up in a ``papagai/<branchname>-<date-time>-<uuid>``
branch and the ``papagai/latest`` branch will be updated to point to that branch.


.. contents:: Table of Contents

papagai code
------------

Run Claude with a programming primer that provides best practices guidance.
This primer is automatically prepended to your instructions, allowing you to
focus on the specific task.

.. code-block:: console

   $ papagai code [OPTIONS] [INSTRUCTIONS_FILE]

**Options:**

* ``--branch, -b BRANCH``: Branch to merge work into (``.`` means current branch)
* ``--dry-run``: Show what would be done without executing

**Arguments:**

* ``INSTRUCTIONS_FILE``: Optional path to a markdown file with instructions. If not provided, will prompt for input.

.. note:: Note that the primer is a relatively generic set of instructions. For complex
          tasks it may be better to use the ``task`` command and custom primers.

**Examples:**

Interactive mode (prompts for instructions):

.. code-block:: console

   $ papagai code
   Please tell me what you want me to do (Ctrl+D to complete)
   Update all .format() strings with f-strings

From a file:

.. code-block:: console

   $ echo "Update all .format() strings with f-strings" > task.md
   $ papagai code task.md


If you are confident in Claude's ability to write code you can ask ``papagai``
to merge the results directly into a local branch. If the branch does not
exist yet it will be created.

.. code-block:: console

   $ papagai code --branch newfeature  implement-my-new-feature.md

Instruction files can include YAML frontmatter to control behavior. For example:
to add to the tools Claude can use:

.. code-block:: markdown

   ---
   tools: Bash(uv :*)
   ---
   Update all dependencies using uv

This **adds** the ``uv`` command via Bash to the tools Claude may use.

papagai do
----------

Run Claude without the programming primer for more general tasks.

.. code-block:: console

   $ papagai do [OPTIONS] [INSTRUCTIONS_FILE]

**Options:**

Same as ``papagai code``.

**Description:**

The ``do`` command works exactly like ``code`` but does not include the
programming primer. Use this when you want full control over the instructions
or for non-programming tasks.

**Example:**

.. code-block:: console

   $ echo "You are a native Spanish speaker. Translate all strings to Spanish" > translate.md
   $ papagai do translate.md

papagai task
------------

Run pre-written tasks from built-in or custom task libraries.

.. code-block:: console

   $ papagai task [OPTIONS] [TASK_NAME]

**Options:**

* ``--list``: List all available tasks
* ``--branch, -b BRANCH``: Base branch to work from

**Arguments:**

* ``TASK_NAME``: Name of the task to run (e.g., ``python/update-to-3.9``)

**Description:**

Tasks are markdown files. Some built-in tasks are shipped with papagai
but you may add your own custom tasks as
``$XDG_CONFIG_HOME/papagai/tasks/**/*.md``.

**Examples:**

List available tasks:

.. code-block:: console

   $ papagai task --list
   Built-in tasks:
     python/update-to-3.9  ... Update a Python code base to Python 3.9+
     c/modernize           ... Modernize C code to C11 standards

   User tasks:
     myproject/refactor    ... Refactor myproject code

Run a task:

.. code-block:: console

   $ papagai task python/update-to-3.9

**Task Structure**

Tasks are markdown files with YAML frontmatter:

.. code-block:: markdown

   ---
   description: A short description of what this task does
   tools: Bash(git:*), Read, Write, Edit  # Optional: tool restrictions
   ---

   # Task Instructions

   You are an expert programmer. Please analyze this codebase and...

The ``description`` field is required and is shown in the task list.

**Variable Substitution:**

Tasks support variable substitution:

* ``{BRANCH}`` - Original branch name
* ``{WORKTREE_BRANCH}`` - Current worktree branch name

papagai review
--------------

Run Claude with a primer that provides best practices guidance for code
reviews.


.. code-block:: console

   $ papagai review [OPTIONS]

**Options:**

* ``--branch, -b BRANCH``: Branch to merge work into (``.`` means current branch)
* ``--dry-run``: Show what would be done without executing
* ``--mr MR_ID``: Merge request ID to review (e.g., ``--mr 1234``)


**Description:**

This command reviews all commits on the current branch, providing inline
feedback and creating fixup commits for any issues found on the ``papagai``
branch.

The ``--mr`` option allows you to review a merge request directly by its ID.
This requires your repository to be configured to fetch merge requests. To
enable this, add the merge request fetch configuration:

.. code-block:: console

   $ git config --add remote.origin.fetch "+refs/merge-requests/*/head:refs/remotes/origin/mr/*"

This maps GitLab merge requests to local refs like ``origin/mr/1234``. The
``--mr`` option cannot be used together with the ``--ref`` option.

**Examples:**

Review the current branch:

.. code-block:: console

   $ papagai review

Review a specific merge request:

.. code-block:: console

   $ papagai review --mr 1234

papagai purge
-------------

Clean up papagai branches.

.. code-block:: console

   $ papagai purge [OPTIONS]

**Options:**

* ``--no-branches``: Do not delete any ``papagai`` git branches
* ``--no-overlays``: Do not unmount any overlays
* ``--no-worktrees``: Do not delete any git worktrees
* ``--dry-run``: Show what would be deleted without actually deleting

**Description:**

Removes all ``papagai`` branches, git worktrees and overlays. Use this to clean
up branches created by papagai after you've merged or reviewed the changes.

**Example:**

.. code-block:: console

   $ papagai purge
   Deleting branch papagai/main-20251112-1030-7be3946e
   Deleting branch papagai/main-20251113-1445-abc123fe
