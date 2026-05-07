#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

import enum
import logging
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import click

try:
    import rich.logging

    handler = rich.logging.RichHandler(rich_tracebacks=True)
except ModuleNotFoundError:
    handler = logging.StreamHandler()


from .cmd import run_command
from .markdown import MarkdownInstructions
from .tracking import record_invocation
from .worktree import BRANCH_PREFIX, Worktree, WorktreeOverlayFs

logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[handler],
)
logger = logging.getLogger("papagai")


@dataclass
class Context:
    dry_run: bool = False
    quiet: bool = False
    notify: bool = False
    model: str | None = None
    track: bool = False

    def echo(self, message: str, **kwargs) -> None:
        """Echo a message unless quiet mode is enabled."""
        if self.quiet:
            return
        click.echo(message, **kwargs)

    def secho(self, message: str, **kwargs) -> None:
        """Echo a styled message unless quiet mode is enabled."""
        # Always show errors (err=True), suppress others in quiet mode
        if kwargs.get("err", False):
            click.secho(message, **kwargs)
        elif self.quiet:
            return
        else:
            click.secho(message, **kwargs)


def send_notification(command: str, directory: str) -> None:
    """Send a desktop notification when a command completes."""
    try:
        import asyncio

        async def _send_notification_async(command: str, directory: str) -> None:
            """Async implementation of notification sending."""
            from desktop_notifier import DesktopNotifier, Notification

            notifier = DesktopNotifier(app_name="papagai")
            message = f"Finished {command} in {directory}/"
            notification = Notification(title=f"papagai {command}", message=message)
            await notifier.send_notification(notification)

        asyncio.run(_send_notification_async(command, directory))

    except ModuleNotFoundError:
        pass


ALLOWED_TOOLS = [
    "Glob",
    "Grep",
    "Read",
    "Bash(git status)",
    "Bash(git diff:*)",
    "Bash(git log:*)",
    "Bash(git show:*)",
    "Bash(git add:*)",
    "Bash(git commit:*)",
    "Bash(uv :*)",
    "Bash(pytest3 :*)",
    "Edit(./**)",
    "Write(./**)",
]

PROMPT_SUFFIX = """

# Important

Any changes to this repository should be committed into git following git best
practices:
- use descriptive subject lines
- group logical changes together
"""


class Isolation(enum.StrEnum):
    AUTO = "auto"
    WORKTREE = "worktree"
    OVERLAYFS = "overlayfs"


def get_builtin_tasks_dir() -> Path:
    package_dir = Path(__file__).parent
    return package_dir / "tasks"


def get_builtin_primers_dir() -> Path:
    package_dir = Path(__file__).parent
    return package_dir / "primers"


def get_xdg_task_dir() -> Path:
    return (
        Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config"))
        / "papagai"
        / "tasks"
    )


def get_branch(repo_dir: Path, ref: str = "HEAD") -> str:
    """
    Get the branch name for a given ref (commit-ish).

    Args:
        repo_dir: Path to git repository
        ref: Git ref (branch name, HEAD, etc.). Default: HEAD

    Returns:
        The branch name

    Raises:
        subprocess.CalledProcessError if ref doesn't exist or not a git repo
    """
    result = run_command(
        ["git", "rev-parse", "--abbrev-ref", "--verify", ref],
        cwd=repo_dir,
    )
    return result.stdout.strip()


def get_mr_fetch_prefix(repo_dir: Path, remote: str = "origin") -> str | None:
    """
    Get the local prefix for merge request refs from git config.

    Parses git config to find the merge request fetch configuration for the
    specified remote. For example, a fetch config like:
        +refs/merge-requests/*/head:refs/remotes/origin/mr/*
    would return "origin/mr".

    Args:
        repo_dir: Path to git repository
        remote: Git remote name (default: origin)

    Returns:
        The local prefix for merge requests (e.g., "origin/mr"), or None if not configured

    Raises:
        subprocess.CalledProcessError if git command fails
    """
    result = run_command(
        ["git", "config", "--get-regexp", f"^remote.{remote}.fetch"],
        cwd=repo_dir,
        check=False,
    )

    if result.returncode != 0:
        return None

    # Parse the fetch lines to find merge request configuration
    # GitLab format: remote.origin.fetch +refs/merge-requests/*/head:refs/remotes/origin/mr/*
    # GitHub format: remote.origin.fetch +refs/pull/*/head:refs/remotes/origin/mr/*
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue

        # Split into key and value
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue

        value = parts[1]

        # Check if this is a merge request fetch line
        if ("merge-requests" in value or "pull" in value) and ":refs/remotes/" in value:
            # Extract the local ref prefix after the colon
            # Format: +refs/merge-requests/*/head:refs/remotes/origin/mr/*
            _, local_ref = value.split(":", 1)
            # Remove the refs/remotes/ prefix and the /* suffix
            # refs/remotes/origin/mr/* -> origin/mr
            if local_ref.startswith("refs/remotes/"):
                local_ref = local_ref[len("refs/remotes/") :]
            if local_ref.endswith("/*"):
                local_ref = local_ref[:-2]
            return local_ref

    return None


def branch_exists(repo_dir: Path, branch: str) -> bool:
    result = run_command(
        ["git", "rev-parse", "--verify", f"refs/heads/{branch}"],
        cwd=repo_dir,
        check=False,
    )
    return result.returncode == 0


def create_branch_if_not_exists(
    repo_dir: Path, branch_spec: str | None, base_branch: str
) -> str:
    # None or "." means use current branch
    if branch_spec is None or branch_spec == ".":
        return base_branch

    if branch_exists(repo_dir, branch_spec):
        return branch_spec

    logger.debug(f"Creating new branch: {branch_spec} from {base_branch}")
    run_command(
        ["git", "branch", branch_spec, base_branch],
        cwd=repo_dir,
    )
    return branch_spec


def merge_into_target_branch(repo_dir: Path, dest: str, src: str) -> int:
    result = run_command(
        [
            "git",
            "merge-base",
            "--is-ancestor",
            dest,
            src,
        ],
        cwd=repo_dir,
        check=False,
    )
    if result.returncode != 0:
        click.secho(
            f"Error: Cannot fast-forward {dest} to {src}",
            err=True,
            fg="red",
        )
        click.secho(
            "The branches have diverged. Manual merge required.",
            err=True,
            fg="red",
        )
        return 1

    # Check if target branch is currently checked out
    try:
        current_checkout = get_branch(repo_dir, "HEAD")
        is_checked_out = current_checkout == dest
    except subprocess.CalledProcessError:
        is_checked_out = False

    try:
        if is_checked_out:
            # Use git merge if the target branch is currently checked out
            run_command(
                ["git", "merge", "--ff-only", src],
                cwd=repo_dir,
            )
        else:
            # Use internal fetch if the target branch is not checked out
            run_command(
                ["git", "fetch", ".", f"{src}:{dest}"],
                cwd=repo_dir,
            )
    except subprocess.CalledProcessError as e:
        click.secho(
            f"Error: Failed to merge {src} into {dest}: {e}",
            err=True,
            fg="red",
        )
        click.secho(
            f"Work is available in branch {src}",
            err=True,
            fg="yellow",
        )
        return 1
    return 0


def purge_branches(ctx: Context, repo_dir: Path) -> None:
    """
    Delete all papagai branches from the repository.
    """
    result = run_command(
        ["git", "branch", "--format=%(refname:short)", "--list", f"{BRANCH_PREFIX}/*"],
        cwd=repo_dir,
    )
    branches = result.stdout.strip().split("\n")
    for branch in [b for b in branches if b]:
        ctx.echo(f"Deleting branch: {branch}")
        run_command(["git", "branch", "-D", branch], cwd=repo_dir, check=False)


def purge_worktrees(ctx: Context, repo_dir: Path) -> None:
    """
    Remove any leftover git worktrees created by papagai.
    """
    result = run_command(
        ["git", "worktree", "list", "--porcelain"],
        cwd=repo_dir,
    )

    # Parse worktree list output
    # Format is: worktree <path>\nHEAD <sha>\nbranch <branch>\n\n
    worktrees = []
    current_worktree = {}
    for line in result.stdout.strip().split("\n"):
        if line.startswith("worktree "):
            if current_worktree:
                worktrees.append(current_worktree)
            current_worktree = {"path": line.split(" ", 1)[1]}
        elif line.startswith("branch "):
            current_worktree["branch"] = line.split(" ", 1)[1]

    if current_worktree:
        worktrees.append(current_worktree)

    for worktree in worktrees:
        branch = worktree.get("branch", "")

        if branch.startswith(f"refs/heads/{BRANCH_PREFIX}/"):
            path = worktree.get("path", "")
            ctx.echo(f"Removing worktree: {path} (branch: {branch})")
            run_command(
                ["git", "worktree", "remove", "--force", path],
                cwd=repo_dir,
                check=False,
            )


def purge_overlays(ctx: Context, repo_dir: Path) -> None:
    """
    Remove and unmount any leftover overlayfs created by papagai.
    """
    xdg_cache_home = (
        Path(os.getenv("XDG_CACHE_HOME", Path.home() / ".cache")) / "papagai"
    )
    overlay_base = xdg_cache_home / repo_dir.name

    if not overlay_base.exists():
        return

    # Find all overlay directories
    if WorktreeOverlayFs.get_fusermount_binary() is None:
        logger.error("Neither fusermount3 nor fusermount is available on the system")
        return

    dirs = list(overlay_base.glob("**/mounted"))
    for mount_dir in dirs:
        if not mount_dir.is_dir():
            continue

        ctx.echo(f"Unmounting overlay: {mount_dir}")
        result = WorktreeOverlayFs.umount_directory(mount_dir, check=False)
        if result.returncode == 0:
            ctx.echo(f"Removing overlay directory: {mount_dir.parent}")
            shutil.rmtree(mount_dir.parent, ignore_errors=True)
        else:
            logger.warning(f"Failed to unmount {mount_dir}, it may not be mounted")


def run_claude(
    ctx: Context,
    worktree_dir: Path,
    instructions: str,
    dry_run: bool,
    allowed_tools: list[str] | None = None,
    model: str | None = None,
) -> None:
    """Run the Claude review agent."""
    if allowed_tools is None:
        allowed_tools = []

    cmd = [
        "claude",
        "--allowed-tools",
        " ".join(allowed_tools),
        "-p",
        instructions,
    ]

    if model:
        cmd.extend(["--model", model])

    if dry_run:
        ctx.echo("Would execute command:")
        ctx.echo(f"  cd {shlex.quote(str(worktree_dir))}")
        ctx.echo(f"  {' '.join(shlex.quote(arg) for arg in cmd)}")
        return

    ctx.secho(
        "Claude is pondering, contemplating, mulling, puzzling, meditating, etc.",
        fg="blue",
    )

    try:
        result = run_command(cmd, cwd=worktree_dir)
        if result.stdout:
            click.echo(result.stdout)
        if result.stderr:
            click.secho(result.stderr, err=True, fg="red")
    except subprocess.CalledProcessError as e:
        click.secho(f"Error running claude: {e}", err=True, fg="red")
        if e.stdout:
            click.echo(e.stdout)
        if e.stderr:
            click.secho(e.stderr, err=True, fg="red")
        raise


def claude_run(
    ctx: Context,
    base_branch: str,
    instructions: MarkdownInstructions,
    dry_run: bool,
    branch_prefix: str = "",
    isolation: Isolation = Isolation.AUTO,
    keep: bool = False,
    target_branch: str | None = None,
    mr_number: int | None = None,
    model: str | None = None,
    command: str = "",
    task_name: str | None = None,
) -> int:
    # Resolve repository directory
    repo_dir = Path.cwd().resolve()
    if not repo_dir.is_dir():
        click.secho(f"Error: {repo_dir} is not a directory", err=True, fg="red")
        return 1

    try:
        current_branch = get_branch(repo_dir, base_branch)
        if not current_branch:
            # If we get here we've already verified that it's a valid git
            # ref but it may just be that - a ref. There's probably a better
            # way to do this than to manually handle HEAD but oh well.
            current_branch = base_branch
            if not target_branch:
                if base_branch.startswith("HEAD"):
                    target_branch = base_branch.replace("HEAD", "head").replace(
                        "~", "-"
                    )
                else:
                    target_branch = base_branch
    except subprocess.CalledProcessError:
        click.secho(
            f"Error: Unable to find branch {base_branch} in this repo",
            err=True,
            fg="red",
        )
        return 1

    # Handle target branch: create if needed, or use existing
    try:
        work_base_branch = create_branch_if_not_exists(
            repo_dir, target_branch, current_branch
        )
    except subprocess.CalledProcessError as e:
        click.secho(
            f"Error: Failed to create or access target branch: {e}",
            err=True,
            fg="red",
        )
        return 1

    worktree_class = Worktree
    if isolation in [Isolation.AUTO, Isolation.OVERLAYFS]:
        if WorktreeOverlayFs.is_supported():
            worktree_class = WorktreeOverlayFs
            # OverlayFS requires .git to be a directory so it can be
            # overlaid. If .git is a gitlink file (as in git worktrees
            # and submodules), git operations inside the overlay follow
            # the gitlink to the real .git directory outside the
            # overlay, bypassing isolation.
            if not (repo_dir / ".git").is_dir():
                logger.warning(
                    "OverlayFS requires .git to be a directory, using normal worktrees"
                )
                worktree_class = Worktree
        elif isolation != Isolation.AUTO:
            click.secho(
                "Error: fuse-overlayfs is not available. Please install it or use --isolation=worktree",
                err=True,
                fg="red",
            )
            return 1
        else:
            worktree_class = Worktree
        if isolation == Isolation.AUTO:
            logger.debug(f"Using isolation {worktree_class.__name__}")
    elif isolation == Isolation.WORKTREE:
        worktree_class = Worktree
    else:
        raise NotImplementedError(f"Error: Invalid isolation mode {isolation}")

    def _track(branch: str) -> None:
        if not ctx.track or dry_run:
            return
        try:
            record_invocation(
                command=command,
                branch=branch,
                directory=str(repo_dir),
                task_name=task_name,
            )
        except Exception as e:
            logger.warning(f"Failed to record invocation: {e}")

    allowed_tools = ALLOWED_TOOLS + instructions.tools
    try:
        with worktree_class.from_branch(
            repo_dir,
            work_base_branch,
            branch_prefix=f"{BRANCH_PREFIX}/{branch_prefix}",
            keep=keep,
            mr_number=mr_number,
        ) as worktree:
            ctx.secho(
                f"Working in branch {worktree.branch} (based off {work_base_branch})",
                bold=True,
            )

            assert instructions.text
            insts = instructions.text.replace("{BRANCH}", work_base_branch)
            insts = insts.replace("{WORKTREE_BRANCH}", worktree.branch)
            insts = f"{insts}\n{PROMPT_SUFFIX}"

            run_claude(ctx, worktree.worktree_dir, insts, dry_run, allowed_tools, model)

            # Save the worktree branch before context manager exits
            worktree_branch = worktree.branch
            worktree_obj = worktree

        if not dry_run and not worktree_obj.has_commits():
            click.secho(
                f"Error: no commits on branch {worktree_branch}",
                err=True,
                fg="red",
            )
            _track(worktree_branch)
            return 1

        ctx.secho(
            f"My work here is done. Check out branch {work_base_branch if target_branch else worktree_branch} or papagai/latest",
            bold=True,
        )

        _track(worktree_branch)

        # After worktree cleanup, merge work branch into target branch if specified
        if target_branch is not None:
            return merge_into_target_branch(
                repo_dir, dest=work_base_branch, src=worktree_branch
            )

        return 0
    except AssertionError as e:
        raise e
    except Exception as e:
        click.secho(f"Error: {e}", err=True, fg="red")
        return 1


def list_all_tasks(ctx: Context) -> int:
    """
    List all available tasks from the instructions directory.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    # Find the instructions directory from the installed package
    builtin_tasks_dir = get_builtin_tasks_dir()
    if not builtin_tasks_dir.exists() or not builtin_tasks_dir.is_dir():
        click.secho(
            f"Error: Tasks directory not found at {builtin_tasks_dir}",
            err=True,
            fg="red",
        )
        return 1

    all_dirs = [builtin_tasks_dir]
    xdg_dir = get_xdg_task_dir()
    if xdg_dir.exists():
        all_dirs = [xdg_dir] + all_dirs

    @dataclass
    class Task:
        name: str
        description: str

    tasks: list[Task] = []
    for dir in all_dirs:
        md_files = sorted(dir.glob("**/*.md"))
        if not md_files:
            continue

        for md_file in md_files:
            try:
                md = MarkdownInstructions.from_file(md_file)
                if md.description:
                    # Get relative path from instructions directory without .md extension
                    rel_path = md_file.relative_to(dir)
                    task_name = str(rel_path.with_suffix(""))
                    tasks.append(Task(task_name, md.description))
                else:
                    click.secho(
                        f"Found task file {md_file} but it doesn't have a description",
                        err=True,
                    )
            except Exception as e:
                click.secho(
                    f"Warning: Failed to parse {md_file}: {e}", err=True, fg="red"
                )

    if not tasks:
        click.secho("No tasks with descriptions found.", err=True, fg="red")
        return 1

    # Calculate the maximum task name length for alignment
    max_name_len = max(len(task.name) for task in tasks)

    # Print tasks with aligned descriptions
    for task in tasks:
        ctx.echo(f"{task.name:<{max_name_len}} ... {task.description}")

    return 0


@click.group(invoke_without_command=False)
@click.option("-v", "--verbose", count=True, help="increase verbosity")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show the claude command that would be executed without running it",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Suppress informational messages (keeps errors and Claude's output)",
)
@click.option(
    "--notify",
    is_flag=True,
    help="Send desktop notification when command completes",
)
@click.option(
    "--model",
    default=None,
    help="Model to use for Claude (e.g., sonnet, opus, haiku)",
)
@click.option(
    "--track",
    is_flag=True,
    help="Record this invocation in the tracking database",
)
@click.pass_context
def papagai(
    ctx: click.Context,
    dry_run: bool,
    verbose: int,
    quiet: bool,
    notify: bool,
    model: str | None,
    track: bool,
) -> None:
    """Papagai: Automate code changes with Claude AI on git worktrees."""

    if quiet:
        # In quiet mode, only show warnings and errors
        logger.setLevel(logging.WARNING)
    else:
        verbose_levels = {0: logging.ERROR, 1: logging.INFO, 2: logging.DEBUG}
        logger.setLevel(verbose_levels.get(verbose, logging.DEBUG))

    logger.debug(f"Verbose level set {logger.getEffectiveLevel()}")
    # Store context object for subcommands
    ctx.obj = Context(
        dry_run=dry_run, quiet=quiet, notify=notify, model=model, track=track
    )


@papagai.result_callback()
@click.pass_context
def process_result(ctx: click.Context, result: int, **_kwargs) -> None:
    """Process the result from subcommands to set the exit code."""
    if ctx.obj and ctx.obj.notify and ctx.invoked_subcommand:
        # Send desktop notification
        directory = Path.cwd().name
        command = ctx.invoked_subcommand
        logger.debug(f"Attempting to send notification for command: {command}")
        try:
            send_notification(command, directory)
        except OSError as e:
            # Handle notification system unavailability (e.g., no D-Bus on Linux)
            logger.warning(f"Failed to send notification: {e}")
        except RuntimeError as e:
            # Handle asyncio-related errors
            logger.warning(f"Failed to send notification: {e}")

    if result is not None:
        ctx.exit(result)


@papagai.command("do")
@click.argument(
    "instructions_file",
    type=click.Path(exists=True, path_type=Path),
    required=False,
)
@click.option(
    "--base-branch",
    default="HEAD",
    help="Branch to base the work on (default: current branch)",
)
@click.option(
    "-b",
    "--branch",
    "target_branch",
    default=None,
    help="Target branch to work on (creates if needed, merges work into it)",
)
@click.option(
    "--isolation",
    type=click.Choice(["auto", "worktree", "overlayfs"], case_sensitive=False),
    default="auto",
    help="Worktree isolation mode: auto (try overlayfs, fall back to worktree), worktree (git worktree), or overlayfs (fuse-overlayfs)",
)
@click.option(
    "--keep/--no-keep",
    default=False,
    help="Keep the worktree/overlay after completion (default: --no-keep)",
)
@click.pass_context
def cmd_do(
    ctx: click.Context,
    instructions_file: Path | None,
    base_branch: str,
    target_branch: str | None,
    isolation: str,
    keep: bool,
) -> int:
    """
    Tell Claude to do something non-code related on a work tree.

    This is the command for non-coding related tasks, and the instructions
    should include priming Claude for the task at hand.

    See papagai code for programming tasks.
    """

    if instructions_file is not None:
        try:
            instructions = MarkdownInstructions.from_file(instructions_file)
        except (FileNotFoundError, PermissionError) as e:
            click.secho(f"Error reading instructions file: {e}", err=True, fg="red")
            return 1
    else:
        if sys.stdin.isatty():
            ctx.obj.secho(
                "Please tell me what you want me to do (Ctrl+D to complete)",
                bold=True,
            )
        instructions = MarkdownInstructions(text=sys.stdin.read())

    if not instructions.text:
        click.secho(
            "Empty instructions. That's it, I can't work under these conditions!",
            err=True,
            fg="red",
        )
        return 1

    return claude_run(
        ctx=ctx.obj,
        base_branch=base_branch,
        instructions=instructions,
        dry_run=ctx.obj.dry_run,
        isolation=Isolation(isolation),
        keep=keep,
        target_branch=target_branch,
        model=ctx.obj.model,
        command="do",
    )


@papagai.command("code")
@click.argument(
    "instructions_file",
    type=click.Path(exists=True, path_type=Path),  # type: ignore[type-var]
    required=False,
)
@click.option(
    "--base-branch",
    default="HEAD",
    help="Branch to base the work on (default: current branch)",
)
@click.option(
    "-b",
    "--branch",
    "target_branch",
    default=None,
    help="Target branch to work on (creates if needed, merges work into it)",
)
@click.option(
    "--isolation",
    type=click.Choice(["auto", "worktree", "overlayfs"], case_sensitive=False),
    default="auto",
    help="Worktree isolation mode: auto (try overlayfs, fall back to worktree), worktree (git worktree), or overlayfs (fuse-overlayfs)",
)
@click.option(
    "--keep/--no-keep",
    default=False,
    help="Keep the worktree/overlay after completion (default: --no-keep)",
)
@click.pass_context
def cmd_code(
    ctx: click.Context,
    instructions_file: Path | None,
    base_branch: str,
    target_branch: str | None,
    isolation: str,
    keep: bool,
) -> int:
    """
    Tell Claude to code something on a work tree.

    This command primes Claude to be software developer with an automatically
    inserted prompt prefix. The provided instructions thus only need to focus on
    the actual code.

    See papagai do for non-coding tasks.
    """

    if instructions_file is not None:
        try:
            instructions = MarkdownInstructions.from_file(instructions_file)
        except (FileNotFoundError, PermissionError) as e:
            click.secho(f"Error reading instructions file: {e}", err=True, fg="red")
            return 1
    else:
        if sys.stdin.isatty():
            ctx.obj.secho(
                "Please tell me what you want me to do (Ctrl+D to complete)",
                bold=True,
            )
        instructions = MarkdownInstructions(text=sys.stdin.read())

    if not instructions.text:
        click.secho(
            "Empty instructions. That's it, I can't work under these conditions!",
            err=True,
            fg="red",
        )
        return 1

    primer = MarkdownInstructions.from_file(get_builtin_primers_dir() / "code.md")
    instructions = primer.combine(instructions)

    return claude_run(
        ctx=ctx.obj,
        base_branch=base_branch,
        instructions=instructions,
        dry_run=ctx.obj.dry_run,
        isolation=Isolation(isolation),
        keep=keep,
        target_branch=target_branch,
        model=ctx.obj.model,
        command="code",
    )


@papagai.command("purge")
@click.option(
    "--branches/--no-branches",
    default=True,
    help="Remove git branches created by papagai (default: --branches)",
)
@click.option(
    "--worktrees/--no-worktrees",
    default=True,
    help="Remove leftover git worktrees created by papagai (default: --worktrees)",
)
@click.option(
    "--overlays/--no-overlays",
    default=True,
    help="Remove and unmount leftover overlayfs created by papagai (default: --overlays)",
)
@click.pass_context
def cmd_purge(
    ctx: click.Context, branches: bool, worktrees: bool, overlays: bool
) -> int:
    """
    Clean up papagai artifacts: branches, worktrees, and overlayfs.

    By default, removes all types of artifacts. Use --no-* flags to skip specific types.
    """
    repo_dir = Path.cwd().resolve()
    if not repo_dir.is_dir():
        click.secho(f"Error: {repo_dir} is not a directory", err=True, fg="red")
        return 1

    error_occurred = False

    if branches:
        try:
            purge_branches(ctx.obj, repo_dir)
        except subprocess.CalledProcessError as e:
            click.secho(f"Error purging branches: {e}", err=True, fg="red")
            error_occurred = True

    if worktrees:
        try:
            purge_worktrees(ctx.obj, repo_dir)
        except subprocess.CalledProcessError as e:
            click.secho(f"Error purging worktrees: {e}", err=True, fg="red")
            error_occurred = True

    if overlays:
        try:
            purge_overlays(ctx.obj, repo_dir)
        except Exception as e:
            click.secho(f"Error purging overlays: {e}", err=True, fg="red")
            error_occurred = True

    return 1 if error_occurred else 0


@papagai.command("task")
@click.option(
    "--list",
    "list_tasks",
    is_flag=True,
    help="List all available tasks",
)
@click.option(
    "--base-branch",
    default="HEAD",
    help="Branch to base the work on (default: current branch)",
)
@click.argument("task_name", required=False)
@click.pass_context
def cmd_task(
    ctx: click.Context,
    list_tasks: bool,
    base_branch: str,
    task_name: str | None,
) -> int:
    """
    Run a pre-written task, either from the built-in list or from tasks in
    XDG_CONFIG_HOME/papagai/tasks/**/*.md.

    Use --list to see all available tasks.
    """
    if list_tasks:
        return list_all_tasks(ctx.obj)

    if not task_name:
        click.secho(
            "Error: missing task name. Available tasks:",
            err=True,
            fg="red",
        )
        return list_all_tasks(ctx.obj)

    # Resolve repository directory
    repo_dir = Path.cwd().resolve()
    if not repo_dir.is_dir():
        click.secho(f"Error: {repo_dir} is not a directory", err=True, fg="red")
        return 1

    # Resolve task to instructions file from installed package
    task_files = [
        get_xdg_task_dir() / f"{task_name}.md",
        get_builtin_tasks_dir() / f"{task_name}.md",
    ]

    task_file = next((f for f in task_files if f.exists()), None)
    if not task_file:
        click.secho(
            f"Error: Task '{task_name}' not found",
            err=True,
            fg="red",
        )
        click.secho(
            "Run 'papagai task --list' to see available tasks",
            err=True,
            fg="red",
        )
        return 1
    try:
        instructions = MarkdownInstructions.from_file(task_file)
    except (FileNotFoundError, PermissionError) as e:
        click.secho(f"Error reading instructions file: {e}", err=True, fg="red")
        return 1

    return claude_run(
        ctx=ctx.obj,
        base_branch=base_branch,
        instructions=instructions,
        dry_run=ctx.obj.dry_run,
        model=ctx.obj.model,
        command="task",
        task_name=task_name,
    )


@papagai.command("review")
@click.option(
    "--ref",
    default="HEAD",
    help="Git ref (branch, commit SHA, or tag) to review (default: HEAD)",
)
@click.option(
    "--mr",
    type=int,
    default=None,
    help="Merge request ID to review (e.g., 1234)",
)
@click.option(
    "-b",
    "--branch",
    "target_branch",
    default=None,
    help="Target branch to work on (creates if needed, merges work into it)",
)
@click.option(
    "--isolation",
    type=click.Choice(["auto", "worktree", "overlayfs"], case_sensitive=False),
    default="auto",
    help="Worktree isolation mode: auto (try overlayfs, fall back to worktree), worktree (git worktree), or overlayfs (fuse-overlayfs)",
)
@click.option(
    "--keep/--no-keep",
    default=False,
    help="Keep the worktree/overlay after completion (default: --no-keep)",
)
@click.option(
    "-n",
    "--num-commits",
    "num_commits",
    type=click.IntRange(min=1),
    default=None,
    help="Review only the top N commits on the branch (default: all commits)",
)
@click.pass_context
def cmd_review(
    ctx: click.Context,
    ref: str,
    mr: int | None,
    target_branch: str | None,
    isolation: str,
    keep: bool,
    num_commits: int | None,
) -> int:
    """
    Run a code review on the specified git ref (branch, commit, or tag).
    """
    # Resolve repository directory
    repo_dir = Path.cwd().resolve()
    if not repo_dir.is_dir():
        click.secho(f"Error: {repo_dir} is not a directory", err=True, fg="red")
        return 1

    # Handle --mr option
    if mr is not None:
        # Check if both --ref and --mr are specified
        if ref != "HEAD":
            click.secho(
                "Error: Cannot use both --ref and --mr options together",
                err=True,
                fg="red",
            )
            return 1

        # Get the merge request fetch prefix
        mr_prefix = get_mr_fetch_prefix(repo_dir)
        if mr_prefix is None:
            click.secho(
                "This repo is not configured to fetch merge requests. Run the following command:",
                err=True,
                fg="red",
            )
            click.secho(
                '  GitLab: git config --add remote.origin.fetch "+refs/merge-requests/*/head:refs/remotes/origin/mr/*"',
                err=True,
                fg="yellow",
            )
            click.secho(
                '  GitHub: git config --add remote.origin.fetch "+refs/pull/*/head:refs/remotes/origin/mr/*"',
                err=True,
                fg="yellow",
            )
            click.secho("Then run git fetch to fetch.", err=True, fg="yellow")
            return 1

        # Construct the merge request ref
        ref = f"{mr_prefix}/{mr}"

    try:
        get_branch(repo_dir, ref)
    except subprocess.CalledProcessError:
        click.secho(
            f"Error: '{ref}' is not a valid git reference",
            err=True,
            fg="red",
        )
        return 1

    primers_dir = get_builtin_primers_dir()
    review_task_file = primers_dir / "review.md"

    if not review_task_file.exists():
        click.secho(
            f"Error: Review task not found at {review_task_file}. This is a bug",
            err=True,
            fg="red",
        )
        return 1

    try:
        instructions = MarkdownInstructions.from_file(review_task_file)
    except (FileNotFoundError, PermissionError) as e:
        click.secho(f"Error reading review instructions: {e}", err=True, fg="red")
        return 1

    if num_commits is not None:
        num_commits_instruction = (
            f"Review only the top {num_commits} commits on the current branch "
            f"(use `git log -{num_commits}` to get them)."
        )
    else:
        num_commits_instruction = (
            "Use `git log` to find all new commits on the current branch that "
            "are not in the main/master branch."
        )
    instructions.text = instructions.text.replace(
        "{NUM_COMMITS_INSTRUCTION}", num_commits_instruction
    )

    return claude_run(
        ctx=ctx.obj,
        base_branch=ref,
        instructions=instructions,
        dry_run=ctx.obj.dry_run,
        branch_prefix="review/",
        isolation=Isolation(isolation),
        keep=keep,
        target_branch=target_branch,
        mr_number=mr,
        model=ctx.obj.model,
        command="review",
        task_name=f"mr{mr}" if mr is not None else None,
    )


@papagai.command("tracker")
def cmd_tracker() -> int:
    """Browse invocation history in an interactive TUI.

    Requires the 'textual' package (install with: pip install papagai[tracker]).
    """
    try:
        from .tracker_tui import run_tracker
    except ImportError:
        click.secho(
            "Error: the 'textual' package is required for the tracker TUI.\n"
            "Install it with: pip install papagai[tracker]",
            err=True,
            fg="red",
        )
        return 1

    run_tracker()
    return 0


if __name__ == "__main__":
    sys.exit(papagai())
