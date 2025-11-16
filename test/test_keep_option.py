#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the --keep option across CLI and worktree functionality."""

import logging
import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from papagai.cli import papagai
from papagai.worktree import BRANCH_PREFIX, LATEST_BRANCH, Worktree, WorktreeOverlayFs

logger = logging.getLogger("papagai.test")


@pytest.fixture
def mock_git_repo(tmp_path):
    """Create a mock git repository directory."""
    repo_dir = tmp_path / "test-repo"
    repo_dir.mkdir()
    return repo_dir


@pytest.fixture
def real_git_repo(tmp_path):
    """Create a real git repository for integration tests."""
    repo_dir = tmp_path / "test-repo"
    repo_dir.mkdir()

    # Initialize git repository
    subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    # Configure git user for commits
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    # Create an initial commit
    test_file = repo_dir / "README.md"
    test_file.write_text("# Test Repository\n")
    subprocess.run(
        ["git", "add", "README.md"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    return repo_dir


class TestCLIKeepOptionHelp:
    """Test --keep option appears in help for CLI commands."""

    @pytest.fixture
    def runner(self):
        """Create a CliRunner instance."""
        return CliRunner()

    @pytest.mark.parametrize("command", ["do", "code", "review"])
    def test_keep_option_in_help(self, runner, command):
        """Test --keep option appears in help for do, code, and review commands."""
        result = runner.invoke(papagai, [command, "--help"])
        assert result.exit_code == 0
        assert "--keep" in result.output
        assert "--no-keep" in result.output
        assert "default: --no-keep" in result.output


class TestCLIKeepOptionPassedToClaudeRun:
    """Test --keep option is correctly passed to claude_run() from CLI commands."""

    @pytest.fixture
    def runner(self):
        """Create a CliRunner instance."""
        return CliRunner()

    @pytest.fixture
    def mock_instructions_file(self, tmp_path):
        """Create a temporary instructions file."""
        instructions = tmp_path / "instructions.md"
        instructions.write_text(
            """---
description: Test task
tools: Bash(test:*)
---

Do something interesting.
"""
        )
        return instructions

    @pytest.mark.parametrize("command", ["do", "code"])
    def test_keep_true_passed_to_claude_run(
        self, runner, command, mock_instructions_file
    ):
        """Test --keep flag is passed correctly to claude_run for do and code commands."""
        with patch("papagai.cli.claude_run") as mock_claude_run:
            mock_claude_run.return_value = 0

            result = runner.invoke(
                papagai,
                [command, "--keep", str(mock_instructions_file)],
            )

            mock_claude_run.assert_called_once()
            call_kwargs = mock_claude_run.call_args[1]
            assert call_kwargs["keep"] is True
            assert result.exit_code == 0

    @pytest.mark.parametrize("command", ["do", "code"])
    def test_no_keep_passed_to_claude_run(
        self, runner, command, mock_instructions_file
    ):
        """Test --no-keep flag is passed correctly to claude_run for do and code commands."""
        with patch("papagai.cli.claude_run") as mock_claude_run:
            mock_claude_run.return_value = 0

            result = runner.invoke(
                papagai,
                [command, "--no-keep", str(mock_instructions_file)],
            )

            mock_claude_run.assert_called_once()
            call_kwargs = mock_claude_run.call_args[1]
            assert call_kwargs["keep"] is False
            assert result.exit_code == 0

    @pytest.mark.parametrize("command", ["do", "code"])
    def test_default_is_no_keep(self, runner, command, mock_instructions_file):
        """Test that default behavior is --no-keep for do and code commands."""
        with patch("papagai.cli.claude_run") as mock_claude_run:
            mock_claude_run.return_value = 0

            result = runner.invoke(
                papagai,
                [command, str(mock_instructions_file)],
            )

            mock_claude_run.assert_called_once()
            call_kwargs = mock_claude_run.call_args[1]
            assert call_kwargs["keep"] is False
            assert result.exit_code == 0

    def test_review_keep_true_passed_to_claude_run(self, runner):
        """Test --keep flag is passed correctly to claude_run for review command."""
        with patch("papagai.cli.claude_run") as mock_claude_run:
            with patch("papagai.cli.get_builtin_primers_dir") as mock_get_dir:
                # Create a mock primers directory
                mock_dir = MagicMock()
                mock_get_dir.return_value = mock_dir

                # Mock the review primer file
                mock_task_file = MagicMock()
                mock_task_file.exists.return_value = True
                mock_dir.__truediv__.return_value = mock_task_file

                with patch(
                    "papagai.cli.MarkdownInstructions.from_file"
                ) as mock_from_file:
                    mock_instructions = MagicMock()
                    mock_from_file.return_value = mock_instructions
                    mock_claude_run.return_value = 0

                    result = runner.invoke(papagai, ["review", "--keep"])

                    mock_claude_run.assert_called_once()
                    call_kwargs = mock_claude_run.call_args[1]
                    assert call_kwargs["keep"] is True
                    assert result.exit_code == 0

    def test_review_no_keep_passed_to_claude_run(self, runner):
        """Test --no-keep flag is passed correctly to claude_run for review command."""
        with patch("papagai.cli.claude_run") as mock_claude_run:
            with patch("papagai.cli.get_builtin_primers_dir") as mock_get_dir:
                # Create a mock primers directory
                mock_dir = MagicMock()
                mock_get_dir.return_value = mock_dir

                # Mock the review primer file
                mock_task_file = MagicMock()
                mock_task_file.exists.return_value = True
                mock_dir.__truediv__.return_value = mock_task_file

                with patch(
                    "papagai.cli.MarkdownInstructions.from_file"
                ) as mock_from_file:
                    mock_instructions = MagicMock()
                    mock_from_file.return_value = mock_instructions
                    mock_claude_run.return_value = 0

                    result = runner.invoke(papagai, ["review", "--no-keep"])

                    mock_claude_run.assert_called_once()
                    call_kwargs = mock_claude_run.call_args[1]
                    assert call_kwargs["keep"] is False
                    assert result.exit_code == 0

    def test_review_default_is_no_keep(self, runner):
        """Test that default behavior is --no-keep for review command."""
        with patch("papagai.cli.claude_run") as mock_claude_run:
            with patch("papagai.cli.get_builtin_primers_dir") as mock_get_dir:
                # Create a mock primers directory
                mock_dir = MagicMock()
                mock_get_dir.return_value = mock_dir

                # Mock the review primer file
                mock_task_file = MagicMock()
                mock_task_file.exists.return_value = True
                mock_dir.__truediv__.return_value = mock_task_file

                with patch(
                    "papagai.cli.MarkdownInstructions.from_file"
                ) as mock_from_file:
                    mock_instructions = MagicMock()
                    mock_from_file.return_value = mock_instructions
                    mock_claude_run.return_value = 0

                    result = runner.invoke(papagai, ["review"])

                    mock_claude_run.assert_called_once()
                    call_kwargs = mock_claude_run.call_args[1]
                    assert call_kwargs["keep"] is False
                    assert result.exit_code == 0


class TestWorktreeKeepCleanupBehavior:
    """Test Worktree._cleanup() behavior with keep parameter."""

    @pytest.fixture
    def mock_worktree_keep_true(self, mock_git_repo):
        """Create a mock Worktree instance with keep=True."""
        worktree_dir = mock_git_repo / "papagai" / "main-20250101-1200-abc123"
        branch = "papagai/main-20250101-1200-abc123"
        return Worktree(
            worktree_dir=worktree_dir,
            branch=branch,
            repo_dir=mock_git_repo,
            keep=True,
        )

    @pytest.fixture
    def mock_worktree_keep_false(self, mock_git_repo):
        """Create a mock Worktree instance with keep=False."""
        worktree_dir = mock_git_repo / "papagai" / "main-20250101-1200-abc123"
        branch = "papagai/main-20250101-1200-abc123"
        return Worktree(
            worktree_dir=worktree_dir,
            branch=branch,
            repo_dir=mock_git_repo,
            keep=False,
        )

    def test_cleanup_with_keep_true_skips_removal(self, mock_worktree_keep_true):
        """Test cleanup with keep=True skips directory removal but updates latest branch."""
        # Create the worktree directory
        mock_worktree_keep_true.worktree_dir.mkdir(parents=True)

        with patch("papagai.worktree.run_command") as mock_run:
            # Mock git diff to succeed (no changes)
            result = MagicMock()
            result.returncode = 0
            mock_run.return_value = result

            mock_worktree_keep_true._cleanup()

            # Should call:
            # 1. git diff --quiet --exit-code
            # 2. git branch -f papagai/latest <branch> (from repoint_latest_branch)
            # Should NOT call git worktree remove
            assert mock_run.call_count == 2
            calls = mock_run.call_args_list

            # Check git diff was called
            assert calls[0][0][0][0] == "git"
            assert calls[0][0][0][1] == "diff"
            assert "--quiet" in calls[0][0][0]

            # Check git branch -f was called (latest branch update)
            assert calls[1][0][0][0] == "git"
            assert calls[1][0][0][1] == "branch"
            assert calls[1][0][0][2] == "-f"
            assert calls[1][0][0][3] == LATEST_BRANCH

            # Verify git worktree remove was NOT called
            remove_calls = [c for c in calls if "remove" in c[0][0]]
            assert len(remove_calls) == 0

        # Directory should still exist
        assert mock_worktree_keep_true.worktree_dir.exists()

    def test_cleanup_with_keep_true_logs_message(self, mock_worktree_keep_true, caplog):
        """Test cleanup with keep=True logs a message about keeping worktree."""
        mock_worktree_keep_true.worktree_dir.mkdir(parents=True)

        with patch("papagai.worktree.run_command") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            with caplog.at_level(logging.INFO, logger="papagai.worktree"):
                mock_worktree_keep_true._cleanup()

            log_output = caplog.text
            assert "Keeping worktree" in log_output
            assert str(mock_worktree_keep_true.worktree_dir) in log_output

    def test_cleanup_with_keep_false_removes_directory(self, mock_worktree_keep_false):
        """Test cleanup with keep=False removes directory as normal."""
        # Create worktree directory with a file
        mock_worktree_keep_false.worktree_dir.mkdir(parents=True)
        test_file = mock_worktree_keep_false.worktree_dir / "test.txt"
        test_file.write_text("test content")

        with patch("papagai.worktree.run_command") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            mock_worktree_keep_false._cleanup()

            # Directory should be removed
            assert not mock_worktree_keep_false.worktree_dir.exists()

            # Verify git worktree remove was called
            calls = mock_run.call_args_list
            remove_calls = [
                c for c in calls if len(c[0][0]) > 2 and c[0][0][2] == "remove"
            ]
            assert len(remove_calls) == 1

    def test_cleanup_with_keep_true_still_commits_changes(
        self, mock_worktree_keep_true, caplog
    ):
        """Test cleanup with keep=True still commits uncommitted changes."""
        mock_worktree_keep_true.worktree_dir.mkdir(parents=True)

        with patch("papagai.worktree.run_command") as mock_run:
            # Track which commands are being called
            call_count = [0]

            def run_side_effect(cmd, **kwargs):
                call_count[0] += 1
                # First call is git diff - return non-zero to indicate changes present
                if call_count[0] == 1 and cmd[1] == "diff":
                    result = MagicMock()
                    result.returncode = 1
                    return result
                # All other calls succeed
                return MagicMock()

            mock_run.side_effect = run_side_effect

            with caplog.at_level(logging.WARNING, logger="papagai.worktree"):
                mock_worktree_keep_true._cleanup()

            # Should call:
            # 1. git diff --quiet --exit-code (returns 1)
            # 2. git add -A
            # 3. git commit -m "FIXME: changes left in worktree"
            # 4. git branch -f papagai/latest <branch>
            # Should NOT call git worktree remove
            assert mock_run.call_count == 4

            # Check that git add and git commit were called
            calls = mock_run.call_args_list
            add_call = calls[1][0][0]
            commit_call = calls[2][0][0]

            assert add_call == ["git", "add", "-A"]
            assert commit_call == [
                "git",
                "commit",
                "-m",
                "FIXME: changes left in worktree",
            ]

            # Check warning message
            log_output = caplog.text
            assert "Uncommitted changes found in worktree" in log_output
            assert "committing them" in log_output


class TestWorktreeOverlayFsKeepCleanupBehavior:
    """Test WorktreeOverlayFs._cleanup() behavior with keep parameter."""

    @pytest.fixture
    def mock_overlay_fs_keep_true(self, mock_git_repo, tmp_path):
        """Create a mock WorktreeOverlayFs instance with keep=True."""
        overlay_base = tmp_path / "overlay"
        mount_dir = overlay_base / "mounted"
        return WorktreeOverlayFs(
            worktree_dir=mount_dir,
            branch="test-branch",
            repo_dir=mock_git_repo,
            keep=True,
            overlay_base_dir=overlay_base,
            mount_dir=mount_dir,
        )

    @pytest.fixture
    def mock_overlay_fs_keep_false(self, mock_git_repo, tmp_path):
        """Create a mock WorktreeOverlayFs instance with keep=False."""
        overlay_base = tmp_path / "overlay"
        mount_dir = overlay_base / "mounted"
        return WorktreeOverlayFs(
            worktree_dir=mount_dir,
            branch="test-branch",
            repo_dir=mock_git_repo,
            keep=False,
            overlay_base_dir=overlay_base,
            mount_dir=mount_dir,
        )

    def test_cleanup_with_keep_true_skips_unmount(self, mock_overlay_fs_keep_true):
        """Test cleanup with keep=True skips unmounting but updates latest branch."""
        mock_overlay_fs_keep_true.mount_dir.mkdir(parents=True)

        with patch("papagai.worktree.run_command") as mock_run:
            # Track which commands are being called
            call_count = [0]

            def run_side_effect(cmd, **kwargs):
                call_count[0] += 1
                # First call is git diff - no changes
                if call_count[0] == 1 and cmd[1] == "diff":
                    result = MagicMock()
                    result.returncode = 0
                    return result
                # All other calls succeed
                return MagicMock()

            mock_run.side_effect = run_side_effect

            mock_overlay_fs_keep_true._cleanup()

            # Should call:
            # 1. git diff --quiet --exit-code (returns 0)
            # 2. git fetch (pull branch from overlay)
            # 3. git rev-parse --verify (verify branch)
            # 4. git branch -f papagai/latest <branch>
            # Should NOT call fusermount -u
            assert mock_run.call_count == 4

            calls = mock_run.call_args_list

            # Verify fusermount was NOT called
            unmount_calls = [c for c in calls if c[0][0][0] == "fusermount"]
            assert len(unmount_calls) == 0

            # Verify latest branch was updated
            branch_calls = [
                c for c in calls if len(c[0][0]) > 1 and c[0][0][1] == "branch"
            ]
            assert len(branch_calls) == 1
            assert branch_calls[0][0][0][3] == LATEST_BRANCH

        # Directory should still exist
        assert mock_overlay_fs_keep_true.overlay_base_dir.exists()

    def test_cleanup_with_keep_true_logs_message(
        self, mock_overlay_fs_keep_true, caplog
    ):
        """Test cleanup with keep=True logs a message about keeping overlay."""
        mock_overlay_fs_keep_true.mount_dir.mkdir(parents=True)

        with patch("papagai.worktree.run_command") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            with caplog.at_level(logging.INFO, logger="papagai.worktree"):
                mock_overlay_fs_keep_true._cleanup()

            log_output = caplog.text
            assert "Keeping overlay mounted" in log_output
            assert str(mock_overlay_fs_keep_true.mount_dir) in log_output

    def test_cleanup_with_keep_false_unmounts_and_removes(
        self, mock_overlay_fs_keep_false
    ):
        """Test cleanup with keep=False unmounts and removes directories."""
        overlay_base = mock_overlay_fs_keep_false.overlay_base_dir
        mount_dir = mock_overlay_fs_keep_false.mount_dir
        overlay_base.mkdir(parents=True)
        mount_dir.mkdir(parents=True)

        # Create some files in the overlay directory
        (overlay_base / "upperdir").mkdir()
        (overlay_base / "workdir").mkdir()
        (overlay_base / "upperdir" / "test.txt").write_text("test")

        with patch("papagai.worktree.run_command") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            mock_overlay_fs_keep_false._cleanup()

            # Find the fusermount call
            calls = mock_run.call_args_list
            unmount_calls = [c for c in calls if c[0][0][0] == "fusermount"]
            assert len(unmount_calls) == 1
            assert unmount_calls[0][0][0] == ["fusermount", "-u", str(mount_dir)]

            # Directory should be removed
            assert not overlay_base.exists()

    def test_cleanup_with_keep_true_still_commits_changes(
        self, mock_overlay_fs_keep_true, caplog
    ):
        """Test cleanup with keep=True still commits uncommitted changes."""
        mock_overlay_fs_keep_true.mount_dir.mkdir(parents=True)

        with patch("papagai.worktree.run_command") as mock_run:
            # Track which commands are being called
            call_count = [0]

            def run_side_effect(cmd, **kwargs):
                call_count[0] += 1
                # First call is git diff - return non-zero to indicate changes present
                if call_count[0] == 1 and cmd[1] == "diff":
                    result = MagicMock()
                    result.returncode = 1
                    return result
                # All other calls succeed
                return MagicMock()

            mock_run.side_effect = run_side_effect

            with caplog.at_level(logging.WARNING, logger="papagai.worktree"):
                mock_overlay_fs_keep_true._cleanup()

            # Should call:
            # 1. git diff --quiet --exit-code (returns 1)
            # 2. git add -A
            # 3. git commit -m "FIXME: changes left in worktree"
            # 4. git fetch (pull branch from overlay)
            # 5. git rev-parse --verify (verify branch)
            # 6. git branch -f papagai/latest <branch>
            # Should NOT call fusermount -u
            assert mock_run.call_count == 6

            # Check that git add and git commit were called
            calls = mock_run.call_args_list
            add_call = calls[1][0][0]
            commit_call = calls[2][0][0]

            assert add_call == ["git", "add", "-A"]
            assert commit_call == [
                "git",
                "commit",
                "-m",
                "FIXME: changes left in worktree",
            ]

            # Check warning message
            log_output = caplog.text
            assert "Uncommitted changes found in worktree" in log_output


@patch.dict(os.environ, {"XDG_CACHE_HOME": "/tmp/test-cache"})
@pytest.mark.parametrize("worktree_type", [Worktree, WorktreeOverlayFs])
class TestWorktreeIntegrationWithKeep:
    """Integration tests for Worktree and WorktreeOverlayFs with keep option."""

    def test_worktree_with_keep_true_leaves_directory(
        self, real_git_repo, worktree_type
    ):
        """Test worktree with keep=True leaves directory in place after cleanup."""
        with worktree_type.from_branch(
            real_git_repo, "main", branch_prefix=f"{BRANCH_PREFIX}/", keep=True
        ) as worktree:
            # Make a commit
            test_file = worktree.worktree_dir / "test.txt"
            test_file.write_text("test content\n")
            subprocess.run(
                ["git", "add", "test.txt"],
                cwd=worktree.worktree_dir,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "Test commit"],
                cwd=worktree.worktree_dir,
                check=True,
                capture_output=True,
            )

            worktree_dir = worktree.worktree_dir
            branch = worktree.branch

        # After cleanup, worktree directory should still exist for git worktree
        # For overlayfs, the mount should still be mounted
        if worktree_type == Worktree:
            assert worktree_dir.exists()
            # Verify the test file is there
            assert (worktree_dir / "test.txt").exists()
        else:
            # For overlayfs, check mount dir exists
            assert worktree_dir.exists()

        # Verify latest branch was updated
        result = subprocess.run(
            ["git", "rev-parse", LATEST_BRANCH],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        latest_commit = result.stdout.strip()

        result = subprocess.run(
            ["git", "rev-parse", branch],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        branch_commit = result.stdout.strip()

        assert latest_commit == branch_commit

    def test_worktree_with_keep_false_removes_directory(
        self, real_git_repo, worktree_type
    ):
        """Test worktree with keep=False removes directory after cleanup."""
        with worktree_type.from_branch(
            real_git_repo, "main", branch_prefix=f"{BRANCH_PREFIX}/", keep=False
        ) as worktree:
            # Make a commit
            test_file = worktree.worktree_dir / "test.txt"
            test_file.write_text("test content\n")
            subprocess.run(
                ["git", "add", "test.txt"],
                cwd=worktree.worktree_dir,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "Test commit"],
                cwd=worktree.worktree_dir,
                check=True,
                capture_output=True,
            )

            worktree_dir = worktree.worktree_dir
            if worktree_type == WorktreeOverlayFs:
                overlay_base_dir = worktree.overlay_base_dir

        # After cleanup, directories should be removed
        if worktree_type == Worktree:
            assert not worktree_dir.exists()
        else:
            # For overlayfs, overlay base dir should be removed
            assert not overlay_base_dir.exists()

    def test_worktree_with_keep_true_commits_and_updates_latest(
        self, real_git_repo, worktree_type
    ):
        """Test worktree with keep=True still commits changes and updates latest branch."""
        with worktree_type.from_branch(
            real_git_repo, "main", branch_prefix=f"{BRANCH_PREFIX}/", keep=True
        ) as worktree:
            # Make changes
            test_file = worktree.worktree_dir / "test.txt"
            test_file.write_text("test content\n")
            subprocess.run(
                ["git", "add", "test.txt"],
                cwd=worktree.worktree_dir,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "Test commit"],
                cwd=worktree.worktree_dir,
                check=True,
                capture_output=True,
            )

            branch = worktree.branch

        # Verify the branch exists in main repo
        result = subprocess.run(
            ["git", "rev-parse", "--verify", branch],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
        )
        assert result.returncode == 0

        # Verify latest branch points to worktree branch
        latest_commit = subprocess.run(
            ["git", "rev-parse", LATEST_BRANCH],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        branch_commit = subprocess.run(
            ["git", "rev-parse", branch],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        assert latest_commit == branch_commit

    def test_worktree_with_keep_true_handles_uncommitted_changes(
        self, real_git_repo, worktree_type, caplog
    ):
        """Test worktree with keep=True commits uncommitted changes and keeps directory."""
        worktree = worktree_type.from_branch(
            real_git_repo, "main", branch_prefix=f"{BRANCH_PREFIX}/", keep=True
        )

        with caplog.at_level(logging.WARNING, logger="papagai.worktree"), worktree:
            # Create uncommitted changes
            readme_file = worktree.worktree_dir / "README.md"
            readme_file.write_text("# Modified content\nUncommitted changes\n")

            worktree_dir = worktree.worktree_dir
            branch = worktree.branch

        # Check that cleanup committed the changes
        log_output = caplog.text
        assert "Uncommitted changes found in worktree" in log_output
        assert "committing them" in log_output

        # For Worktree, the branch is still in the worktree, check from there
        # For WorktreeOverlayFs, the branch is fetched to the main repo
        if worktree_type == Worktree:
            # Verify the branch has the FIXME commit in the worktree
            result = subprocess.run(
                ["git", "log", "-1", "--pretty=%B"],
                cwd=worktree_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            commit_message = result.stdout.strip()
            assert commit_message == "FIXME: changes left in worktree"
        else:
            # For overlayfs, verify from main repo
            result = subprocess.run(
                ["git", "log", "-1", "--pretty=%B", branch],
                cwd=real_git_repo,
                check=True,
                capture_output=True,
                text=True,
            )
            commit_message = result.stdout.strip()
            assert commit_message == "FIXME: changes left in worktree"

        # Verify directory still exists
        if worktree_type == Worktree:
            assert worktree_dir.exists()
        else:
            # For overlayfs, mount_dir should still exist
            assert worktree_dir.exists()


class TestWorktreeFromBranchKeepParameter:
    """Test that keep parameter is correctly passed when creating worktrees."""

    def test_worktree_from_branch_accepts_keep_parameter(self, mock_git_repo):
        """Test Worktree.from_branch() accepts keep parameter."""
        with patch("papagai.worktree.run_command") as mock_run:
            mock_run.return_value = MagicMock()

            worktree = Worktree.from_branch(
                mock_git_repo, "main", branch_prefix=f"{BRANCH_PREFIX}/", keep=True
            )

            assert worktree.keep is True

    def test_worktree_from_branch_default_keep_is_false(self, mock_git_repo):
        """Test Worktree.from_branch() defaults to keep=False."""
        with patch("papagai.worktree.run_command") as mock_run:
            mock_run.return_value = MagicMock()

            worktree = Worktree.from_branch(
                mock_git_repo, "main", branch_prefix=f"{BRANCH_PREFIX}/"
            )

            assert worktree.keep is False

    @patch.dict(os.environ, {"XDG_CACHE_HOME": "/tmp/test-cache"})
    def test_overlay_fs_from_branch_accepts_keep_parameter(self, mock_git_repo):
        """Test WorktreeOverlayFs.from_branch() accepts keep parameter."""
        with patch("papagai.worktree.run_command") as mock_run:
            mock_run.return_value = MagicMock()

            overlay_fs = WorktreeOverlayFs.from_branch(
                mock_git_repo, "main", branch_prefix=f"{BRANCH_PREFIX}/", keep=True
            )

            assert overlay_fs.keep is True

    @patch.dict(os.environ, {"XDG_CACHE_HOME": "/tmp/test-cache"})
    def test_overlay_fs_from_branch_default_keep_is_false(self, mock_git_repo):
        """Test WorktreeOverlayFs.from_branch() defaults to keep=False."""
        with patch("papagai.worktree.run_command") as mock_run:
            mock_run.return_value = MagicMock()

            overlay_fs = WorktreeOverlayFs.from_branch(
                mock_git_repo, "main", branch_prefix=f"{BRANCH_PREFIX}/"
            )

            assert overlay_fs.keep is False
