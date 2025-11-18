![Papagai Logo](.assets/papagai.svg)

# papagai

`papagai` is a commandline utility to have [Claude](https://claude.ai/) go off and do something
in a git repository. Any changes made by claude are done in a worktree, allowing multiple tasks
to work simultaneously.

For more documentation, see [papagai on ReadTheDocs](https://papagai.readthedocs.io/en/latest/).

## Installation

```console
$ pip install papagai
```

If running from the git repository, use [uv](https://github.com/astral-sh/uv):

```console
$ uv run papagai
```

## Usage

The primary subcommands are `code` and `do` to get Claude to do something.
They are identical but the `code` command primes Claude to be a half-decent
programmer so you can focus on merely the task instructions.

```console
$ papagai code
Please tell me what you want me to do (Ctrl+D to complete)
Update all .format() strings with f-strings
Working in papagai/main-2025-11-12-7be3946e (based off main)
[...]
My work here is done. Check out branch papagai/main-2025-11-12-7be3946e or papagai/latest

# The same by passing instructions via a file
$ echo "Update all .format() strings with f-strings" > instructions.md
$ papagai code instructions.md
[...]
My work here is done. Check out branch papagai/main-2025-11-12-abc134fe or papagai/latest
```

The `papagai/latest` branch is always updated to point to the most recent
papagai branch.

The `do` command works exactly the same way but it does not prime Claude
so you will have to add this to the task (if need be).

```
# Instructions via a file
$ echo "You are a native spanish speaker. Translate all strings to Spanish" > instructions.md
$ papagai do instructions.md
```

The instructions should be in Markdown. If there is a frontmatter key
`"tools"` it is extracted and passed to Claude as the set of allowed tools.
For example:
```markdown
---
tools: Bash(uv :*)
---
Update all .format() strings with f-strings
```

If you really trust Claude, you can tell it to create a new proper branch
directly or merge the results into the current branch:

```
$ papagai code --branch new-features instructions.md
$ papagai code --branch . instructions.md
```

This will still create the papagai branches but also merge them back
into the given branch (where `.` stands for "current branch").

## Pre-written tasks

The `papagai task` command runs pre-written tasks. These are read from
`$XDG_CONFIG_HOME/papagai/tasks/**/*.md` and must look like this:

```
---
description: some description
---
You are a very smart LLM. Blah blah.
```

Additionally `papagai` ships with built-in tasks. These are tasks that were
(somewhat) successfully used elsewhere and might be useful for other
repos.
```console
$ papagai task --list
[...]
python/update-to-3.9                ... update a Python code base to Python 3.9+
$ papagai task python/update-to-3.9
```
The `--list` command will also list any tasks in `XDG_CONFIG_HOME`.

### Variable substitution in task files

- `{BRANCH}` is replaced with the original branch
- `{WORKTREE_BRANCH}` is replaced with the current working branch

### Code Review

The `review` command is a convenience shortcut for running a code review:
```console
$ papagai review
```

This command will review all commits on the current branch, providing inline
feedback and creating fixup commits for any issues found.

### Cleanup

`papagai` works on branches (and in workdirs), if you want to get rid yourself
of any leftover branches use:
```console
$ papagai purge
```


# Acknowledgements

`papagai` is motivated by and based on
[claude-review-agent](https://github.com/swick/claude-dev-tools/).

Most of `papagai` (especially the tests!) was written using Claude.
