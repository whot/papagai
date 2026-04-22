#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

"""Git worktree management for papagai."""

import logging
import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Self

from .cmd import run_command

logger = logging.getLogger("papagai.worktree")

BRANCH_PREFIX = "papagai"
LATEST_BRANCH = f"{BRANCH_PREFIX}/latest"


def get_next_mr_version(repo_dir: Path, mr_number: int) -> int:
    """
    Get the next version number for a merge request review.

    Searches for existing branches matching papagai/review/mr{number}/v*
    and returns the next version number.

    Args:
        repo_dir: Path to the repository root
        mr_number: Merge request number

    Returns:
        Next version number (starting from 1)
    """
    # List all branches matching the pattern
    result = run_command(
        [
            "git",
            "branch",
            "--format=%(refname:short)",
            "--list",
            f"{BRANCH_PREFIX}/review/mr{mr_number}/v*",
        ],
        cwd=repo_dir,
        check=False,
    )

    if result.returncode != 0 or not result.stdout.strip():
        return 1

    # Extract version numbers from branch names
    versions = []
    for branch in result.stdout.strip().split("\n"):
        # Expected format: papagai/review/mr1234/v1/...
        parts = branch.split("/")
        if len(parts) >= 4 and parts[3].startswith("v"):
            try:
                version = int(parts[3][1:])  # Remove 'v' prefix
                versions.append(version)
            except ValueError:
                continue

    return max(versions) + 1 if versions else 1


def repoint_latest_branch(repo_dir: Path, branch: str) -> None:
    """
    Update the papagai/latest branch to point to the specified branch.

    Removes the papagai/latest branch if it exists, then creates it
    pointing to the same commit as the specified branch.

    Args:
        repo_dir: Path to the repository root
        branch: Branch name to point papagai/latest to
    """
    try:
        run_command(
            ["git", "branch", "-f", LATEST_BRANCH, branch],
            cwd=repo_dir,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        logger.error(f"Warning: Failed to update {LATEST_BRANCH}: {e}")


@dataclass
class Worktree:
    """
    Git worktree context manager for automated branch creation and cleanup.

    Attributes:
        worktree_dir: Path to the worktree directory
        branch: Name of the created branch
        repo_dir: Path to the repository root
        keep: If True, skip worktree directory removal during cleanup
        base_commit: SHA of the base commit when the worktree was created
    """

    worktree_dir: Path
    branch: str
    repo_dir: Path
    keep: bool = False
    base_commit: str | None = None

    @classmethod
    def from_branch(
        cls,
        repo_dir: Path,
        base_branch: str,
        branch_prefix: str | None = None,
        keep: bool = False,
        mr_number: int | None = None,
    ) -> Self:
        """
        Create a new review branch using git worktree.

        Args:
            repo_dir: Path to the repository root
            base_branch: Branch to base the new branch on
            branch_prefix: Optional prefix for the branch name
            keep: If True, skip worktree directory removal during cleanup
            mr_number: Optional merge request number for versioned review branches

        Returns:
            Worktree instance

        Raises:
            subprocess.CalledProcessError: If git worktree creation fails
        """
        assert base_branch is not None
        branch_prefix = branch_prefix or ""

        if mr_number is not None:
            # For MR reviews, use versioned format: papagai/review/mr1234/v1
            version = get_next_mr_version(repo_dir, mr_number)
            branch = f"{branch_prefix}mr{mr_number}/v{version}"
        else:
            # Standard naming: {prefix}{base_branch}-{date}-{rand}
            rand = str(uuid.uuid4()).split("-")[0]
            date = datetime.now().strftime("%Y%m%d-%H%M")
            branch = f"{branch_prefix}{base_branch}-{date}-{rand}"

        worktree_dir = repo_dir / branch

        # Record the base commit SHA before creating the worktree
        base_commit = run_command(
            ["git", "rev-parse", base_branch],
            cwd=repo_dir,
        ).stdout.strip()

        run_command(
            [
                "git",
                "worktree",
                "add",
                "--quiet",
                "-b",
                branch,
                str(worktree_dir),
                base_branch,
            ],
            cwd=repo_dir,
        )

        return cls(
            worktree_dir=worktree_dir,
            branch=branch,
            repo_dir=repo_dir,
            keep=keep,
            base_commit=base_commit,
        )

    def has_commits(self) -> bool:
        """
        Check if the branch has any commits beyond the base commit.

        Returns:
            True if the branch has new commits, False otherwise.
            Also returns True if the base commit is unknown (conservative).
        """
        if self.base_commit is None:
            return True

        result = run_command(
            ["git", "rev-parse", self.branch],
            cwd=self.repo_dir,
            check=False,
        )
        if result.returncode != 0:
            return True

        return result.stdout.strip() != self.base_commit

    def __enter__(self) -> Self:
        """Enter the context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the context manager and cleanup the worktree."""
        self._cleanup()

    def _cleanup(self) -> None:
        """Clean up the worktree and any empty parent directories."""
        try:
            if (
                run_command(
                    ["git", "diff", "--quiet", "--exit-code"],
                    cwd=self.worktree_dir,
                    check=False,
                ).returncode
                != 0
            ):
                logger.warning(
                    "Uncommitted changes found in worktree, committing them."
                )
                try:
                    run_command(
                        ["git", "add", "-A"],
                        cwd=self.worktree_dir,
                        check=True,
                    )
                    run_command(
                        ["git", "commit", "-m", "FIXME: changes left in worktree"],
                        cwd=self.worktree_dir,
                        check=True,
                    )
                except subprocess.SubprocessError as e:
                    logger.error(f"Failed to commit uncommitted changes: {e}")
                    logger.error("To clean up manually, run:")
                    logger.error(f"  $ git worktree remove --force {self.branch}")
                    return

            repoint_latest_branch(self.repo_dir, self.branch)

            # Skip directory cleanup if keep is True
            if self.keep:
                logger.info(f"Keeping worktree at {self.worktree_dir}")
                return

            run_command(
                ["git", "worktree", "remove", "--force", str(self.branch)],
                cwd=self.repo_dir,
                check=False,
            )

            # Remove the worktree directory if it still exists
            if self.worktree_dir.exists():
                shutil.rmtree(self.worktree_dir, ignore_errors=True)

            # Remove empty parent directories up to repo_dir
            current = self.worktree_dir.parent
            while current != self.repo_dir and current.is_relative_to(self.repo_dir):
                try:
                    if current.exists() and not any(current.iterdir()):
                        current.rmdir()
                        current = current.parent
                    else:
                        break
                except OSError:
                    # Directory not empty or other error, stop cleanup
                    break
        except Exception as e:
            logger.error(f"Warning during cleanup: {e}")


@dataclass
class WorktreeOverlayFs(Worktree):
    """
    Git worktree using overlay filesystem (fuse-overlayfs).

    This class creates a copy-on-write worktree using fuse-overlayfs,
    where the original repository is the read-only lower layer and
    modifications are stored in an upper layer.

    Attributes:
        worktree_dir: Path to the mounted overlay directory
        branch: Name of the created branch
        repo_dir: Path to the repository root
        keep: If True, skip unmounting and directory removal during cleanup
        overlay_base_dir: Path to the overlay filesystem base directory
        mount_dir: Path to the mounted overlay filesystem
    """

    overlay_base_dir: Path | None = None
    mount_dir: Path | None = None

    @classmethod
    def get_fusermount_binary(cls) -> str | None:
        """
        Get the available fusermount binary, preferring fusermount3.

        Returns:
            "fusermount3" if available, "fusermount" if available, or None if neither is available
        """
        if shutil.which("fusermount3"):
            return "fusermount3"
        if shutil.which("fusermount"):
            return "fusermount"
        return None

    @staticmethod
    def umount_directory(
        directory: Path, check: bool = False
    ) -> subprocess.CompletedProcess[str]:
        """
        Unmount a fuse-overlayfs directory.

        Args:
            directory: Path to the mounted directory to unmount
            check: If True, raise exception on failure

        Raises:
            RuntimeError: If neither fusermount3 nor fusermount is available
        """
        fusermount = WorktreeOverlayFs.get_fusermount_binary()
        if fusermount is None:
            raise RuntimeError(
                "Neither fusermount3 nor fusermount is available on the system"
            )
        return run_command([fusermount, "-u", str(directory)], check=check)

    def umount(self, check: bool = False) -> None:
        if self.mount_dir is not None:
            self.umount_directory(self.mount_dir, check)

    @classmethod
    def is_supported(cls) -> bool:
        """
        Check if fuse-overlayfs is available on the system.

        Returns:
            True if fuse-overlayfs command is available, False otherwise
        """
        return (
            shutil.which("fuse-overlayfs") is not None
            and cls.get_fusermount_binary() is not None
        )

    @classmethod
    def from_branch(
        cls,
        repo_dir: Path,
        base_branch: str,
        branch_prefix: str | None = None,
        keep: bool = False,
        mr_number: int | None = None,
    ) -> Self:
        """
        Create a new overlay worktree using fuse-overlayfs.

        Directory structure:
        - $XDG_CACHE_HOME/papagai/<project>/<branch>-<date>-<uuid>/
           - upperdir/
           - workdir/  - fuse-overlayfs workdir
           - mounted/  - mount point

        The repo_dir is the read-only lower layer with fuse-overlayfs.

        Args:
            repo_dir: Path to the repository root
            base_branch: Branch to base the new branch on
            branch_prefix: Optional prefix for the branch name
            keep: If True, skip unmounting and directory removal during cleanup
            mr_number: Optional merge request number for versioned review branches

        Returns:
            WorktreeOverlayFs instance with mounted overlay filesystem

        Raises:
            subprocess.CalledProcessError: If git or mount operations fail
            RuntimeError: If fuse-overlayfs is not available
        """
        assert base_branch is not None

        # Record the base commit SHA before creating the worktree
        base_commit = run_command(
            ["git", "rev-parse", base_branch],
            cwd=repo_dir,
        ).stdout.strip()

        # Generate unique directory name using same scheme as Worktree
        rand = str(uuid.uuid4()).split("-")[0]
        date = datetime.now().strftime("%Y%m%d-%H%M")
        # Skip the branch prefix here so we don't nest directories too much
        directory_name = f"{base_branch}-{date}-{rand}"

        xdg_cache_home = (
            Path(os.getenv("XDG_CACHE_HOME", Path.home() / ".cache")) / "papagai"
        )
        overlay_base_dir = xdg_cache_home / repo_dir.name / directory_name
        overlay_base_dir.mkdir(parents=True, exist_ok=True)

        logger.debug(f"Setting up overlayfs in {overlay_base_dir}")

        upperdir = overlay_base_dir / "upperdir"
        workdir = overlay_base_dir / "workdir"
        mount_dir = overlay_base_dir / "mounted"

        upperdir.mkdir(exist_ok=True)
        workdir.mkdir(exist_ok=True)
        mount_dir.mkdir(exist_ok=True)

        # Create branch name with prefix and MR versioning if applicable
        branch_prefix = branch_prefix or ""
        if mr_number is not None:
            # For MR reviews, use versioned format: papagai/review/mr1234/v1
            version = get_next_mr_version(repo_dir, mr_number)
            branch = f"{branch_prefix}mr{mr_number}/v{version}"
        else:
            # Standard naming: {prefix}{base_branch}-{date}-{rand}
            branch = f"{branch_prefix}{directory_name}"

        try:
            run_command(
                [
                    "fuse-overlayfs",
                    "-o",
                    f"lowerdir={repo_dir},upperdir={upperdir},workdir={workdir}",
                    str(mount_dir),
                ]
            )
        except subprocess.CalledProcessError as e:
            # Cleanup directories if mount fails
            shutil.rmtree(overlay_base_dir, ignore_errors=True)
            raise RuntimeError(
                f"Failed to mount overlay filesystem. Is fuse-overlayfs installed? Error: {e}"
            ) from e

        # Create a new git branch in the mounted directory
        try:
            run_command(
                ["git", "checkout", "-fb", branch, base_branch],
                cwd=mount_dir,
            )
        except subprocess.CalledProcessError as e:
            # Cleanup on failure
            cls.umount_directory(mount_dir, check=False)
            shutil.rmtree(overlay_base_dir, ignore_errors=True)
            raise RuntimeError(f"Failed to create git branch: {e}") from e

        return cls(
            worktree_dir=mount_dir,
            branch=branch,
            repo_dir=repo_dir,
            keep=keep,
            base_commit=base_commit,
            overlay_base_dir=overlay_base_dir,
            mount_dir=mount_dir,
        )

    def _log_fusermount_instructions(self):
        fusermount_cmd = self.get_fusermount_binary() or "fusermount"
        logger.error("To clean up the worktree, run:")
        logger.error(f"  $ {fusermount_cmd} -u {self.mount_dir}")
        logger.error(f"  $ rm -rf {self.overlay_base_dir}")

    def _cleanup(self) -> None:
        """Clean up the overlay filesystem and directories."""
        try:
            if (
                run_command(
                    ["git", "diff", "--quiet", "--exit-code"],
                    cwd=self.worktree_dir,
                    check=False,
                ).returncode
                != 0
            ):
                logger.warning(
                    "Uncommitted changes found in worktree, committing them."
                )
                try:
                    run_command(
                        ["git", "add", "-A"],
                        cwd=self.worktree_dir,
                        check=True,
                    )
                    run_command(
                        ["git", "commit", "-m", "FIXME: changes left in worktree"],
                        cwd=self.worktree_dir,
                        check=True,
                    )
                except (RuntimeError, subprocess.SubprocessError) as e:
                    logger.error(f"Failed to commit uncommitted changes: {e}")
                    self._log_fusermount_instructions()
                    return

            # Pull the branch from the overlay into the main repository
            # before unmounting and cleaning up
            try:
                run_command(
                    [
                        "git",
                        "fetch",
                        str(self.mount_dir),
                        f"{self.branch}:{self.branch}",
                    ],
                    cwd=self.repo_dir,
                    check=True,
                )
                # Verify the branch exists in the main repository
                run_command(
                    ["git", "rev-parse", "--verify", self.branch],
                    cwd=self.repo_dir,
                    check=True,
                )
            except subprocess.CalledProcessError as e:
                logger.error(
                    f"Warning: Failed to pull branch {self.branch} from overlay: {e}"
                )
                logger.error("To clean up manually, run:")
                logger.error(
                    f"  $ git fetch {self.mount_dir} {self.branch}:{self.branch}"
                )
                self._log_fusermount_instructions()
                return

            repoint_latest_branch(self.repo_dir, self.branch)

            # Skip unmounting and directory cleanup if keep is True
            if self.keep:
                logger.info(f"Keeping overlay mounted at {self.mount_dir}")
                return

            # Unmount the overlay filesystem
            if self.mount_dir and self.mount_dir.exists():
                try:
                    self.umount(check=True)
                except (RuntimeError, subprocess.CalledProcessError) as e:
                    logger.error(f"Warning: Failed to unmount {self.mount_dir}: {e}")
                    self._log_fusermount_instructions()
                    return

            # Remove the overlay base directory
            if self.overlay_base_dir and self.overlay_base_dir.exists():
                shutil.rmtree(self.overlay_base_dir, ignore_errors=True)

        except Exception as e:
            logger.error(f"Warning during cleanup: {e}")
