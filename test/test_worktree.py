#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for worktree management utilities."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from papagai.worktree import Worktree, BRANCH_PREFIX


@pytest.fixture
def mock_git_repo(tmp_path):
    """Create a mock git repository directory."""
    repo_dir = tmp_path / "test-repo"
    repo_dir.mkdir()
    return repo_dir


@pytest.fixture
def mock_worktree(mock_git_repo):
    """Create a mock Worktree instance."""
    worktree_dir = mock_git_repo / "papagai" / "main-2025-01-01-abc123"
    branch = "papagai/main-2025-01-01-abc123"
    return Worktree(
        worktree_dir=worktree_dir,
        branch=branch,
        repo_dir=mock_git_repo,
    )


class TestWorktreeDataclass:
    """Tests for Worktree dataclass structure."""

    def test_worktree_initialization(self, mock_git_repo):
        """Test Worktree can be initialized with required fields."""
        worktree_dir = mock_git_repo / "test-worktree"
        branch = "papagai/test-branch"

        worktree = Worktree(
            worktree_dir=worktree_dir,
            branch=branch,
            repo_dir=mock_git_repo,
        )

        assert worktree.worktree_dir == worktree_dir
        assert worktree.branch == branch
        assert worktree.repo_dir == mock_git_repo

    def test_worktree_attributes_are_paths(self, mock_worktree):
        """Test that worktree_dir and repo_dir are Path objects."""
        assert isinstance(mock_worktree.worktree_dir, Path)
        assert isinstance(mock_worktree.repo_dir, Path)
        assert isinstance(mock_worktree.branch, str)


class TestFromBranch:
    """Tests for Worktree.from_branch() classmethod."""

    @pytest.mark.parametrize(
        "base_branch", ["main", "develop", "feature/test", "v1.0.0"]
    )
    def test_from_branch_creates_worktree(self, mock_git_repo, base_branch):
        """Test from_branch creates a worktree for different base branches."""
        with patch("papagai.worktree.run_command") as mock_run:
            mock_run.return_value = MagicMock()

            worktree = Worktree.from_branch(
                mock_git_repo, base_branch, branch_prefix=f"{BRANCH_PREFIX}/"
            )

            # Check worktree attributes
            assert worktree.repo_dir == mock_git_repo
            assert worktree.branch.startswith(f"{BRANCH_PREFIX}/{base_branch}")
            assert str(worktree.worktree_dir).startswith(str(mock_git_repo))

            # Verify git command was called
            mock_run.assert_called_once()
            call_args = mock_run.call_args
            assert call_args[0][0][0] == "git"
            assert call_args[0][0][1] == "worktree"
            assert call_args[0][0][2] == "add"
            assert base_branch in call_args[0][0]

    def test_from_branch_creates_unique_branches(self, mock_git_repo):
        """Test from_branch creates unique branch names on each call."""
        with patch("papagai.worktree.run_command"):
            worktree1 = Worktree.from_branch(mock_git_repo, "main")
            worktree2 = Worktree.from_branch(mock_git_repo, "main")

            assert worktree1.branch != worktree2.branch

    def test_from_branch_branch_name_format(self, mock_git_repo):
        """Test that branch names follow the expected format."""
        with patch("papagai.worktree.run_command"):
            worktree = Worktree.from_branch(
                mock_git_repo, "main", branch_prefix=f"{BRANCH_PREFIX}/"
            )

            # Branch should be: papagai/main-YYYY-MM-DD-XXXXXXXX
            parts = worktree.branch.split("/")
            assert len(parts) == 2
            assert parts[0] == BRANCH_PREFIX

            # Second part should be: main-YYYY-MM-DD-XXXXXXXX
            branch_parts = parts[1].split("-")
            assert branch_parts[0] == "main"
            assert len(branch_parts) >= 4  # base-YYYY-MM-DD-uuid

    def test_from_branch_git_command_parameters(self, mock_git_repo):
        """Test that git worktree command is called with correct parameters."""
        with patch("papagai.worktree.run_command") as mock_run:
            worktree = Worktree.from_branch(mock_git_repo, "develop")

            call_args = mock_run.call_args
            git_cmd = call_args[0][0]

            assert git_cmd[0] == "git"
            assert git_cmd[1] == "worktree"
            assert git_cmd[2] == "add"
            assert "--quiet" in git_cmd
            assert "-b" in git_cmd
            assert worktree.branch in git_cmd
            assert str(worktree.worktree_dir) in git_cmd
            assert "develop" in git_cmd

            # Check cwd parameter
            assert call_args[1]["cwd"] == mock_git_repo

    def test_from_branch_raises_on_git_error(self, mock_git_repo):
        """Test from_branch raises CalledProcessError when git fails."""
        with patch("papagai.worktree.run_command") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "git")

            with pytest.raises(subprocess.CalledProcessError):
                Worktree.from_branch(mock_git_repo, "main")


class TestContextManager:
    """Tests for Worktree context manager functionality."""

    def test_context_manager_enter(self, mock_worktree):
        """Test __enter__ returns the Worktree instance."""
        result = mock_worktree.__enter__()
        assert result is mock_worktree

    def test_context_manager_exit_calls_cleanup(self, mock_worktree):
        """Test __exit__ calls _cleanup method."""
        with patch.object(mock_worktree, "_cleanup") as mock_cleanup:
            mock_worktree.__exit__(None, None, None)
            mock_cleanup.assert_called_once()

    def test_context_manager_with_statement(self, mock_git_repo):
        """Test Worktree works correctly in with statement."""
        with patch("papagai.worktree.run_command"):
            worktree = Worktree.from_branch(mock_git_repo, "main")

        with patch.object(worktree, "_cleanup") as mock_cleanup:
            with worktree as wt:
                assert wt is worktree
            mock_cleanup.assert_called_once()

    def test_context_manager_cleanup_on_exception(self, mock_git_repo):
        """Test cleanup is called even when exception occurs in with block."""
        with patch("papagai.worktree.run_command"):
            worktree = Worktree.from_branch(mock_git_repo, "main")

        with patch.object(worktree, "_cleanup") as mock_cleanup:
            try:
                with worktree:
                    raise ValueError("Test exception")
            except ValueError:
                pass
            mock_cleanup.assert_called_once()


class TestCleanup:
    """Tests for Worktree._cleanup() method."""

    def test_cleanup_removes_clean_worktree(self, mock_worktree):
        """Test cleanup removes worktree with no uncommitted changes."""
        # Create the worktree directory
        mock_worktree.worktree_dir.mkdir(parents=True)

        with patch("papagai.worktree.run_command") as mock_run:
            # Mock git diff to succeed (no changes)
            mock_run.return_value = MagicMock()

            mock_worktree._cleanup()

            # Should call git diff and git worktree remove
            assert mock_run.call_count == 2
            calls = mock_run.call_args_list

            # First call: git diff --quiet --exit-code
            assert calls[0][0][0][0] == "git"
            assert calls[0][0][0][1] == "diff"
            assert "--quiet" in calls[0][0][0]

            # Second call: git worktree remove
            assert calls[1][0][0][0] == "git"
            assert calls[1][0][0][1] == "worktree"
            assert calls[1][0][0][2] == "remove"

    def test_cleanup_refuses_with_uncommitted_changes(self, mock_worktree, capsys):
        """Test cleanup refuses to remove worktree with uncommitted changes."""
        mock_worktree.worktree_dir.mkdir(parents=True)

        with patch("papagai.worktree.run_command") as mock_run:
            # Mock git diff to fail (changes present)
            mock_run.side_effect = subprocess.CalledProcessError(1, "git")

            mock_worktree._cleanup()

            # Should only call git diff once, then return
            assert mock_run.call_count == 1

            # Check warning message
            captured = capsys.readouterr()
            assert "Changes still present in worktree" in captured.out
            assert "refusing to clean up" in captured.out
            assert mock_worktree.branch in captured.out

    def test_cleanup_removes_worktree_directory(self, mock_worktree):
        """Test cleanup removes worktree directory if it exists."""
        # Create worktree directory with a file
        mock_worktree.worktree_dir.mkdir(parents=True)
        test_file = mock_worktree.worktree_dir / "test.txt"
        test_file.write_text("test content")

        with patch("papagai.worktree.run_command") as mock_run:
            mock_run.return_value = MagicMock()

            mock_worktree._cleanup()

            # Directory should be removed
            assert not mock_worktree.worktree_dir.exists()

    def test_cleanup_removes_empty_parent_directories(self, mock_worktree):
        """Test cleanup removes empty parent directories up to repo_dir."""
        # Create nested directory structure
        nested_dir = mock_worktree.repo_dir / "a" / "b" / "c"
        nested_dir.mkdir(parents=True)

        # Update worktree to use nested directory
        mock_worktree.worktree_dir = nested_dir

        with patch("papagai.worktree.run_command") as mock_run:
            mock_run.return_value = MagicMock()

            mock_worktree._cleanup()

            # All empty parent directories should be removed
            assert not (mock_worktree.repo_dir / "a").exists()

    def test_cleanup_preserves_non_empty_parent_directories(self, mock_worktree):
        """Test cleanup preserves parent directories that contain other files."""
        # Create nested directory structure
        parent_dir = mock_worktree.repo_dir / "parent"
        parent_dir.mkdir()

        # Add a file in parent directory
        other_file = parent_dir / "other.txt"
        other_file.write_text("other content")

        # Create worktree dir inside parent
        worktree_dir = parent_dir / "worktree"
        worktree_dir.mkdir()
        mock_worktree.worktree_dir = worktree_dir

        with patch("papagai.worktree.run_command") as mock_run:
            mock_run.return_value = MagicMock()

            mock_worktree._cleanup()

            # Parent directory should still exist (not empty)
            assert parent_dir.exists()
            assert other_file.exists()

    def test_cleanup_handles_exceptions_gracefully(self, mock_worktree, capsys):
        """Test cleanup handles exceptions without crashing."""
        with patch("papagai.worktree.run_command") as mock_run:
            mock_run.side_effect = Exception("Unexpected error")

            # Should not raise, just print warning
            mock_worktree._cleanup()

            captured = capsys.readouterr()
            assert "Warning during cleanup" in captured.err

    @pytest.mark.parametrize("check_value", [True, False])
    def test_cleanup_git_worktree_remove_check_parameter(
        self, mock_worktree, check_value
    ):
        """Test that git worktree remove is called with check=False."""
        mock_worktree.worktree_dir.mkdir(parents=True)

        with patch("papagai.worktree.run_command") as mock_run:
            mock_run.return_value = MagicMock()

            mock_worktree._cleanup()

            # Find the git worktree remove call
            calls = mock_run.call_args_list
            remove_call = [c for c in calls if c[0][0][2] == "remove"][0]

            # check should be False
            assert remove_call[1]["check"] is False


class TestIntegration:
    """Integration tests for Worktree."""

    def test_full_workflow_with_context_manager(self, mock_git_repo):
        """Test complete workflow: create, use, cleanup."""
        with patch("papagai.worktree.run_command") as mock_run:
            mock_run.return_value = MagicMock()

            with Worktree.from_branch(
                mock_git_repo, "main", branch_prefix=f"{BRANCH_PREFIX}/"
            ) as worktree:
                # Verify worktree was created
                assert worktree.branch.startswith(f"{BRANCH_PREFIX}/main")
                assert worktree.repo_dir == mock_git_repo

            # Verify cleanup was called (git diff + git worktree remove)
            assert mock_run.call_count >= 2
