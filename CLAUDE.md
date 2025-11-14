# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`papagai` is a CLI tool that runs Claude on git repositories using isolated worktrees. It allows Claude to make changes in separate git worktrees, enabling multiple tasks to run simultaneously without interfering with the main working directory.

### Core Architecture

The project has three main components:

1. **Worktree Management** (`papagai/worktree.py`): Handles git worktree creation, cleanup, and isolation. Two isolation modes are supported:
   - Standard git worktrees (`Worktree` class)
   - Overlay filesystem worktrees (`WorktreeOverlayFs` class) using fuse-overlayfs for copy-on-write functionality

2. **CLI Interface** (`papagai/cli.py`): Provides command-line interface with commands:
   - `papagai code <instructions>` - Run Claude with programming primer
   - `papagai do <instructions>` - Run Claude without primer
   - `papagai task <task-name>` - Run pre-written tasks
   - `papagai review` - Code review convenience command
   - `papagai purge` - Clean up papagai branches

3. **Markdown Parsing** (`papagai/markdown.py`): Parses instruction files with frontmatter support. Frontmatter can include `tools` key for allowed tool restrictions.

### Branch Naming Convention

Worktree branches follow the pattern: `papagai/<prefix><base-branch>-<YYYYmmdd-HHMM>-<uuid>`

Example: `papagai/main-20251114-1030-7be3946e`

A special `papagai/latest` branch always points to the most recent papagai branch.

### Task System

Tasks are markdown files with frontmatter, loaded from:
- Built-in tasks: `papagai/tasks/**/*.md` (shipped with the package)
- User tasks: `$XDG_CONFIG_HOME/papagai/tasks/**/*.md`

Task files support variable substitution:
- `{BRANCH}` - Original branch name
- `{WORKTREE_BRANCH}` - Current worktree branch name

## Development Commands

### Running the Tool

```bash
# From git repository (recommended for development)
uv run papagai <command>

# If installed via pip
papagai <command>
```

### Testing

```bash
# Run all tests
uv run pytest test/ -v

# Run specific test file
uv run pytest test/test_worktree.py -v

# Run specific test
uv run pytest test/test_worktree.py::TestCleanup::test_cleanup_removes_clean_worktree -v
```

### Code Quality

The project uses `ruff` for linting and formatting:

```bash
# Run ruff linter
ruff check .

# Run ruff formatter
ruff format .
```

Pre-commit hooks are configured in `.pre-commit-config.yaml` for:
- end-of-file-fixer
- trailing-whitespace
- ruff (linting)
- ruff-format

### Package Structure

```
papagai/
├── cli.py          # Main CLI commands and entry point
├── worktree.py     # Git worktree management classes
├── markdown.py     # Markdown/frontmatter parsing
├── cmd.py          # Command execution utilities
├── primers/        # Built-in primer templates (code.md, review.md)
└── tasks/          # Built-in task templates (python/, c/, meson/)
```

## Key Implementation Details

## Worktree Behavior

All changes happen exclusively on worktrees (either a git-worktree or an overlayfs).
Those changes are committed to git and pulled back into the main repository as a branch.
Worktrees are removed once the command completes.

The  `papagai/latest` branch always points to the most recent completed work.

### Primer System

The `code` command includes a programming primer (`papagai/primers/code.md`) that instructs Claude on:
- Code quality principles
- Git best practices
- Development workflow
- Testing and documentation standards

This primer is automatically prepended to user instructions.

## Python Version Support

Requires Python 3.10+. The codebase should maintain compatibility across Python 3.10-3.13.

## Dependencies

Core dependencies (from `pyproject.toml`):
- `click` - CLI framework

Dev dependencies:
- `pytest` - Testing framework

Optional runtime:
- `rich` - Enhanced logging output
- `fuse-overlayfs` - For overlay filesystem isolation mode
