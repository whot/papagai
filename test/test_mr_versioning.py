#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for MR versioning functionality."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from papagai.worktree import (
    BRANCH_PREFIX,
    Worktree,
    WorktreeOverlayFs,
    get_next_mr_version,
)


@pytest.fixture
def real_git_repo(tmp_path):
    """Create a real git repository for integration tests."""
    repo_dir = tmp_path / "test-repo"
    repo_dir.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    # Create initial commit
    (repo_dir / "README.md").write_text("# Test Repository\n")
    subprocess.run(
        ["git", "add", "README.md"], cwd=repo_dir, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    return repo_dir


class TestGetNextMrVersion:
    """Tests for get_next_mr_version function."""

    def test_get_next_mr_version_returns_1_for_first_review(self, real_git_repo):
        """Test that get_next_mr_version returns 1 when no previous review exists."""
        version = get_next_mr_version(real_git_repo, 1234)
        assert version == 1

    def test_get_next_mr_version_returns_2_after_v1_exists(self, real_git_repo):
        """Test that get_next_mr_version returns 2 when v1 exists."""
        # Create v1 branch
        subprocess.run(
            ["git", "branch", f"{BRANCH_PREFIX}/review/mr1234/v1"],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
        )

        version = get_next_mr_version(real_git_repo, 1234)
        assert version == 2

    def test_get_next_mr_version_returns_3_after_v1_and_v2_exist(self, real_git_repo):
        """Test that get_next_mr_version returns 3 when v1 and v2 exist."""
        # Create v1 and v2 branches
        subprocess.run(
            ["git", "branch", f"{BRANCH_PREFIX}/review/mr1234/v1"],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "branch", f"{BRANCH_PREFIX}/review/mr1234/v2"],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
        )

        version = get_next_mr_version(real_git_repo, 1234)
        assert version == 3

    def test_get_next_mr_version_handles_different_mr_numbers(self, real_git_repo):
        """Test that get_next_mr_version correctly isolates MR numbers."""
        # Create v1 for MR 1234
        subprocess.run(
            ["git", "branch", f"{BRANCH_PREFIX}/review/mr1234/v1"],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
        )

        # MR 5678 should still get version 1
        version = get_next_mr_version(real_git_repo, 5678)
        assert version == 1

        # MR 1234 should get version 2
        version = get_next_mr_version(real_git_repo, 1234)
        assert version == 2

    def test_get_next_mr_version_ignores_non_versioned_branches(self, real_git_repo):
        """Test that get_next_mr_version ignores branches without version numbers."""
        # Create a branch without proper version format
        subprocess.run(
            ["git", "branch", f"{BRANCH_PREFIX}/review/mr1234/invalid"],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
        )

        version = get_next_mr_version(real_git_repo, 1234)
        assert version == 1

    def test_get_next_mr_version_finds_max_version(self, real_git_repo):
        """Test that get_next_mr_version finds the maximum version."""
        # Create v1, v3, v5 (non-sequential)
        for v in [1, 3, 5]:
            subprocess.run(
                ["git", "branch", f"{BRANCH_PREFIX}/review/mr1234/v{v}"],
                cwd=real_git_repo,
                check=True,
                capture_output=True,
            )

        version = get_next_mr_version(real_git_repo, 1234)
        assert version == 6


class TestWorktreeWithMrNumber:
    """Tests for Worktree.from_branch with mr_number parameter."""

    @patch("papagai.worktree.run_command")
    def test_worktree_from_branch_creates_versioned_branch_name(self, mock_run):
        """Test that Worktree.from_branch creates correct branch name with mr_number."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        repo_dir = Path("/fake/repo")

        # Mock get_next_mr_version to return 1
        with patch("papagai.worktree.get_next_mr_version", return_value=1):
            worktree = Worktree.from_branch(
                repo_dir=repo_dir,
                base_branch="origin/mr/1234",
                branch_prefix="papagai/review/",
                mr_number=1234,
            )

        # Check that the branch name follows the pattern
        assert worktree.branch == "papagai/review/mr1234/v1"

    @patch("papagai.worktree.run_command")
    def test_worktree_from_branch_increments_version(self, mock_run):
        """Test that Worktree.from_branch increments version for subsequent reviews."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        repo_dir = Path("/fake/repo")

        # Mock get_next_mr_version to return 2
        with patch("papagai.worktree.get_next_mr_version", return_value=2):
            worktree = Worktree.from_branch(
                repo_dir=repo_dir,
                base_branch="origin/mr/1234",
                branch_prefix="papagai/review/",
                mr_number=1234,
            )

        assert worktree.branch == "papagai/review/mr1234/v2"

    @patch("papagai.worktree.run_command")
    def test_worktree_from_branch_without_mr_number_uses_standard_naming(
        self, mock_run
    ):
        """Test that Worktree.from_branch uses standard naming without mr_number."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        repo_dir = Path("/fake/repo")

        worktree = Worktree.from_branch(
            repo_dir=repo_dir,
            base_branch="main",
            branch_prefix="papagai/review/",
            mr_number=None,
        )

        # Standard naming should include date and random string
        assert worktree.branch.startswith("papagai/review/main-")
        assert "mr" not in worktree.branch


class TestWorktreeOverlayFsWithMrNumber:
    """Tests for WorktreeOverlayFs.from_branch with mr_number parameter."""

    @patch("papagai.worktree.shutil.which")
    @patch("papagai.worktree.run_command")
    @patch("papagai.worktree.Path.mkdir")
    def test_overlay_fs_from_branch_creates_versioned_branch_name(
        self, mock_mkdir, mock_run, mock_which
    ):
        """Test that WorktreeOverlayFs.from_branch creates correct branch name with mr_number."""
        mock_which.return_value = "/usr/bin/fuse-overlayfs"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        repo_dir = Path("/fake/repo")

        # Mock get_next_mr_version to return 1
        with patch("papagai.worktree.get_next_mr_version", return_value=1):
            worktree = WorktreeOverlayFs.from_branch(
                repo_dir=repo_dir,
                base_branch="origin/mr/1234",
                branch_prefix="papagai/review/",
                mr_number=1234,
            )

        # Check that the branch name follows the pattern
        assert worktree.branch == "papagai/review/mr1234/v1"

    @patch("papagai.worktree.shutil.which")
    @patch("papagai.worktree.run_command")
    @patch("papagai.worktree.Path.mkdir")
    def test_overlay_fs_from_branch_uses_standard_directory_naming(
        self, mock_mkdir, mock_run, mock_which
    ):
        """Test that WorktreeOverlayFs.from_branch uses standard directory naming."""
        mock_which.return_value = "/usr/bin/fuse-overlayfs"
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        repo_dir = Path("/fake/repo")

        # Mock get_next_mr_version to return 1
        with patch("papagai.worktree.get_next_mr_version", return_value=1):
            worktree = WorktreeOverlayFs.from_branch(
                repo_dir=repo_dir,
                base_branch="origin/mr/1234",
                branch_prefix="papagai/review/",
                mr_number=1234,
            )

        # Directory name should still use date-random format, not mr1234
        assert worktree.overlay_base_dir is not None
        assert "mr1234" not in str(worktree.overlay_base_dir)


class TestIntegrationWorktreeWithMrNumber:
    """Integration tests for Worktree with mr_number."""

    def test_worktree_creates_versioned_branch_in_real_repo(self, real_git_repo):
        """Test that Worktree creates a versioned branch in a real repository."""
        with Worktree.from_branch(
            repo_dir=real_git_repo,
            base_branch="main",
            branch_prefix="papagai/review/",
            mr_number=1234,
        ) as worktree:
            # Verify branch exists
            result = subprocess.run(
                ["git", "rev-parse", "--verify", worktree.branch],
                cwd=real_git_repo,
                capture_output=True,
            )
            assert result.returncode == 0

            # Verify branch name format
            assert worktree.branch == "papagai/review/mr1234/v1"

    def test_worktree_increments_version_on_second_review(self, real_git_repo):
        """Test that Worktree increments version for subsequent reviews."""
        # First review
        with Worktree.from_branch(
            repo_dir=real_git_repo,
            base_branch="main",
            branch_prefix="papagai/review/",
            mr_number=1234,
        ) as worktree:
            assert worktree.branch == "papagai/review/mr1234/v1"

        # Second review
        with Worktree.from_branch(
            repo_dir=real_git_repo,
            base_branch="main",
            branch_prefix="papagai/review/",
            mr_number=1234,
        ) as worktree:
            assert worktree.branch == "papagai/review/mr1234/v2"
