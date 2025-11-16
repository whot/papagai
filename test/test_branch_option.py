#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for --branch/-b command-line option functionality."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from papagai.cli import (
    branch_exists,
    create_branch_if_not_exists,
    merge_into_target_branch,
    papagai,
)


@pytest.fixture
def mock_repo(tmp_path):
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


class TestBranchExists:
    """Tests for branch_exists() helper function."""

    @pytest.mark.parametrize(
        "branch,expected", [("main", True), ("does-not-exist", False)]
    )
    def test_branch_exists_returns_true_for_existing_branch(
        self, mock_repo, branch, expected
    ):
        """Test branch_exists returns True when branch exists."""
        with patch("papagai.cli.run_command") as mock_run:
            mock_run.return_value = MagicMock(returncode=0 if expected else 1)

            result = branch_exists(mock_repo, branch)

            assert result == expected
            mock_run.assert_called_once_with(
                ["git", "rev-parse", "--verify", f"refs/heads/{branch}"],
                cwd=mock_repo,
                check=False,
            )

            # Make sure we use the right cwd
            call_args = mock_run.call_args
            assert call_args[1]["cwd"] == mock_repo

    @pytest.mark.parametrize(
        "branch_name",
        [
            "main",
            "develop",
            "feature/test",
            "bugfix/fix-123",
            "release/v1.0.0",
        ],
    )
    def test_branch_exists_with_different_branch_names(self, mock_repo, branch_name):
        """Test branch_exists works with various branch name formats."""
        with patch("papagai.cli.run_command") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            branch_exists(mock_repo, branch_name)

            mock_run.assert_called_once_with(
                ["git", "rev-parse", "--verify", f"refs/heads/{branch_name}"],
                cwd=mock_repo,
                check=False,
            )

    @pytest.mark.parametrize(
        "branch,expected", [("main", True), ("does-not-exist", False)]
    )
    def test_branch_exists_with_real_repo(self, real_git_repo, branch, expected):
        """Test branch_exists with a real git repository."""
        assert branch_exists(real_git_repo, branch) == expected


class TestCreateBranchIfNotExists:
    """Tests for create_branch_if_not_exists() helper function."""

    @pytest.mark.parametrize("spec", [None, "."])
    def test_create_branch_returns_base_when_branch_spec_is_none(self, mock_repo, spec):
        """Test returns base_branch when branch_spec is None."""
        result = create_branch_if_not_exists(mock_repo, spec, "main")
        assert result == "main"

    def test_create_branch_returns_existing_branch_without_creating(self, mock_repo):
        """Test returns branch_spec when it already exists without creating."""
        with patch("papagai.cli.run_command") as mock_run:
            # Mock branch_exists to return True
            mock_run.return_value = MagicMock(returncode=0)

            result = create_branch_if_not_exists(mock_repo, "feature", "main")

            assert result == "feature"
            # Should only call git rev-parse (from branch_exists), not git branch
            assert mock_run.call_count == 1
            assert mock_run.call_args[0][0][1] == "rev-parse"

    def test_create_branch_creates_new_branch_when_not_exists(self, mock_repo):
        """Test creates new branch when it doesn't exist."""
        with patch("papagai.cli.run_command") as mock_run:
            # First call (branch_exists) returns 1, second call (git branch) succeeds
            mock_run.side_effect = [
                MagicMock(returncode=1),  # branch doesn't exist
                MagicMock(returncode=0),  # git branch succeeds
            ]

            result = create_branch_if_not_exists(mock_repo, "new-feature", "main")

            assert result == "new-feature"
            assert mock_run.call_count == 2

            # Second call should be git branch
            git_branch_call = mock_run.call_args_list[1]
            assert git_branch_call[0][0] == ["git", "branch", "new-feature", "main"]
            assert git_branch_call[1]["cwd"] == mock_repo

    @pytest.mark.parametrize(
        "branch_spec,base_branch",
        [
            ("feature", "main"),
            ("bugfix/issue-123", "develop"),
            ("release/v1.0.0", "main"),
            ("test-branch", "feature/parent"),
        ],
    )
    def test_create_branch_with_various_branch_names(
        self, mock_repo, branch_spec, base_branch
    ):
        """Test create_branch_if_not_exists with various branch name formats."""
        with patch("papagai.cli.run_command") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=1),  # branch doesn't exist
                MagicMock(returncode=0),  # git branch succeeds
            ]

            result = create_branch_if_not_exists(mock_repo, branch_spec, base_branch)

            assert result == branch_spec
            git_branch_call = mock_run.call_args_list[1]
            assert git_branch_call[0][0] == ["git", "branch", branch_spec, base_branch]

    def test_create_branch_raises_on_git_error(self, mock_repo):
        """Test create_branch_if_not_exists raises when git branch fails."""
        with patch("papagai.cli.run_command") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=1),  # branch doesn't exist
                subprocess.CalledProcessError(1, "git"),  # git branch fails
            ]

            with pytest.raises(subprocess.CalledProcessError):
                create_branch_if_not_exists(mock_repo, "new-branch", "main")

    def test_create_branch_with_real_repo_creates_branch(self, real_git_repo):
        """Test create_branch_if_not_exists with real git repository."""
        # Create a new branch
        result = create_branch_if_not_exists(real_git_repo, "feature", "main")

        assert result == "feature"

        # Verify branch was created
        assert branch_exists(real_git_repo, "feature") is True

    def test_create_branch_with_real_repo_returns_existing(self, real_git_repo):
        """Test create_branch_if_not_exists returns existing branch."""
        # Create branch first
        subprocess.run(
            ["git", "branch", "existing"],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
        )

        # Call function
        result = create_branch_if_not_exists(real_git_repo, "existing", "main")

        assert result == "existing"


class TestMergeIntoTargetBranch:
    """Tests for merge_into_target_branch() helper function."""

    def test_merge_returns_error_when_branches_diverged(self, mock_repo, capsys):
        """Test merge returns error code when branches have diverged."""
        with patch("papagai.cli.run_command") as mock_run:
            # merge-base --is-ancestor returns non-zero (branches diverged)
            mock_run.return_value = MagicMock(returncode=1)

            result = merge_into_target_branch(mock_repo, "main", "feature")

            assert result == 1
            captured = capsys.readouterr()
            assert "Cannot fast-forward" in captured.err
            assert "branches have diverged" in captured.err

    def test_merge_uses_git_merge_when_target_checked_out(self, mock_repo):
        """Test uses git merge when target branch is currently checked out."""
        with patch("papagai.cli.run_command") as mock_run:
            # Setup: merge-base succeeds, get_branch returns target, merge succeeds
            mock_run.side_effect = [
                MagicMock(returncode=0),  # merge-base --is-ancestor
                MagicMock(stdout="main\n"),  # get_branch (HEAD)
                MagicMock(returncode=0),  # git merge
            ]

            result = merge_into_target_branch(mock_repo, "main", "feature")

            assert result == 0
            # Check that git merge was called
            merge_call = mock_run.call_args_list[2]
            assert merge_call[0][0] == ["git", "merge", "--ff-only", "feature"]
            assert merge_call[1]["cwd"] == mock_repo

    def test_merge_uses_git_fetch_when_target_not_checked_out(self, mock_repo):
        """Test uses git fetch when target branch is not checked out."""
        with patch("papagai.cli.run_command") as mock_run:
            # Setup: merge-base succeeds, get_branch returns different branch, fetch succeeds
            mock_run.side_effect = [
                MagicMock(returncode=0),  # merge-base --is-ancestor
                MagicMock(stdout="develop\n"),  # get_branch (HEAD is develop)
                MagicMock(returncode=0),  # git fetch
            ]

            result = merge_into_target_branch(mock_repo, "main", "feature")

            assert result == 0
            # Check that git fetch was called
            fetch_call = mock_run.call_args_list[2]
            assert fetch_call[0][0] == ["git", "fetch", ".", "feature:main"]
            assert fetch_call[1]["cwd"] == mock_repo

    def test_merge_handles_detached_head(self, mock_repo):
        """Test handles detached HEAD state gracefully."""
        with patch("papagai.cli.run_command") as mock_run:
            # Setup: merge-base succeeds, get_branch raises error (detached HEAD), fetch succeeds
            mock_run.side_effect = [
                MagicMock(returncode=0),  # merge-base --is-ancestor
                subprocess.CalledProcessError(1, "git"),  # get_branch fails
                MagicMock(returncode=0),  # git fetch (fallback)
            ]

            result = merge_into_target_branch(mock_repo, "main", "feature")

            assert result == 0
            # Should use git fetch since it can't determine checkout
            fetch_call = mock_run.call_args_list[2]
            assert fetch_call[0][0] == ["git", "fetch", ".", "feature:main"]

    def test_merge_returns_error_when_merge_fails(self, mock_repo, capsys):
        """Test returns error when git merge fails."""
        with patch("papagai.cli.run_command") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),  # merge-base --is-ancestor
                MagicMock(stdout="main\n"),  # get_branch
                subprocess.CalledProcessError(1, "git"),  # git merge fails
            ]

            result = merge_into_target_branch(mock_repo, "main", "feature")

            assert result == 1
            captured = capsys.readouterr()
            assert "Failed to merge" in captured.err
            assert "Work is available in branch feature" in captured.err

    def test_merge_returns_error_when_fetch_fails(self, mock_repo, capsys):
        """Test returns error when git fetch fails."""
        with patch("papagai.cli.run_command") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0),  # merge-base --is-ancestor
                MagicMock(stdout="develop\n"),  # get_branch
                subprocess.CalledProcessError(1, "git"),  # git fetch fails
            ]

            result = merge_into_target_branch(mock_repo, "main", "feature")

            assert result == 1
            captured = capsys.readouterr()
            assert "Failed to merge" in captured.err
            assert "Work is available in branch feature" in captured.err

    def test_merge_checks_merge_base_first(self, mock_repo):
        """Test merge checks merge-base --is-ancestor before attempting merge."""
        with patch("papagai.cli.run_command") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            merge_into_target_branch(mock_repo, "main", "feature")

            # First call should be merge-base
            first_call = mock_run.call_args_list[0]
            assert first_call[0][0] == [
                "git",
                "merge-base",
                "--is-ancestor",
                "main",
                "feature",
            ]
            assert first_call[1]["cwd"] == mock_repo
            assert first_call[1]["check"] is False

    def test_merge_with_real_repo_succeeds(self, real_git_repo):
        """Test merge with real repository performs fast-forward merge."""
        # Create a feature branch and make a commit
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
        )
        test_file = real_git_repo / "test.txt"
        test_file.write_text("test content\n")
        subprocess.run(
            ["git", "add", "test.txt"],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Add test file"],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
        )

        # Switch back to main
        subprocess.run(
            ["git", "checkout", "main"],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
        )

        # Merge feature into main
        result = merge_into_target_branch(real_git_repo, "main", "feature")

        assert result == 0

        # Verify main has the commit
        log_result = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        assert "Add test file" in log_result.stdout

    def test_merge_with_real_repo_fails_on_diverged_branches(self, real_git_repo):
        """Test merge fails when branches have diverged."""
        # Create feature branch and commit
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
        )
        test_file = real_git_repo / "feature.txt"
        test_file.write_text("feature content\n")
        subprocess.run(
            ["git", "add", "feature.txt"],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Feature commit"],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
        )

        # Switch to main and make a different commit (causing divergence)
        subprocess.run(
            ["git", "checkout", "main"],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
        )
        test_file2 = real_git_repo / "main.txt"
        test_file2.write_text("main content\n")
        subprocess.run(
            ["git", "add", "main.txt"],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Main commit"],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
        )

        # Attempt to merge - should fail
        result = merge_into_target_branch(real_git_repo, "main", "feature")

        assert result == 1


class TestBranchOptionInCommands:
    """Tests for --branch/-b option in CLI commands."""

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
---

Do something interesting.
"""
        )
        return instructions

    @pytest.mark.parametrize("command", ["do", "code", "review"])
    def test_branch_option_appears_in_help(self, runner, command):
        """Test --branch option appears in help for do, code, and review commands."""
        result = runner.invoke(papagai, [command, "--help"])
        assert result.exit_code == 0
        assert "--branch" in result.output or "-b" in result.output
        assert "Target branch to work on" in result.output

    @pytest.mark.parametrize("command", ["do", "code"])
    def test_branch_option_passed_to_claude_run(
        self, runner, command, mock_instructions_file
    ):
        """Test --branch option is passed to claude_run."""
        with patch("papagai.cli.claude_run") as mock_claude_run:
            mock_claude_run.return_value = 0

            result = runner.invoke(
                papagai,
                [command, "--branch", "feature", str(mock_instructions_file)],
            )

            mock_claude_run.assert_called_once()
            call_kwargs = mock_claude_run.call_args[1]
            assert call_kwargs["target_branch"] == "feature"
            assert result.exit_code == 0

    @pytest.mark.parametrize("command", ["do", "code"])
    def test_branch_short_option_works(self, runner, command, mock_instructions_file):
        """Test -b short option works."""
        with patch("papagai.cli.claude_run") as mock_claude_run:
            mock_claude_run.return_value = 0

            result = runner.invoke(
                papagai,
                [command, "-b", "feature", str(mock_instructions_file)],
            )

            mock_claude_run.assert_called_once()
            call_kwargs = mock_claude_run.call_args[1]
            assert call_kwargs["target_branch"] == "feature"
            assert result.exit_code == 0

    def test_review_command_accepts_branch_option(self, runner):
        """Test review command accepts --branch option."""
        with patch("papagai.cli.claude_run") as mock_claude_run:
            with patch("papagai.cli.get_builtin_primers_dir") as mock_get_dir:
                # Mock the review primer file
                mock_dir = MagicMock()
                mock_get_dir.return_value = mock_dir
                mock_task_file = MagicMock()
                mock_task_file.exists.return_value = True
                mock_dir.__truediv__.return_value = mock_task_file

                with patch(
                    "papagai.cli.MarkdownInstructions.from_file"
                ) as mock_from_file:
                    mock_instructions = MagicMock()
                    mock_from_file.return_value = mock_instructions
                    mock_claude_run.return_value = 0

                    result = runner.invoke(
                        papagai,
                        ["review", "--branch", "review-branch"],
                    )

                    mock_claude_run.assert_called_once()
                    call_kwargs = mock_claude_run.call_args[1]
                    assert call_kwargs["target_branch"] == "review-branch"
                    assert result.exit_code == 0

    @pytest.mark.parametrize("command", ["do", "code"])
    def test_branch_option_default_is_none(
        self, runner, command, mock_instructions_file
    ):
        """Test default value for --branch is None."""
        with patch("papagai.cli.claude_run") as mock_claude_run:
            mock_claude_run.return_value = 0

            result = runner.invoke(
                papagai,
                [command, str(mock_instructions_file)],
            )

            mock_claude_run.assert_called_once()
            call_kwargs = mock_claude_run.call_args[1]
            assert call_kwargs["target_branch"] is None
            assert result.exit_code == 0


class TestClaudeRunWithTargetBranch:
    """Integration tests for claude_run with target_branch parameter."""

    @pytest.fixture
    def mock_instructions(self):
        """Create mock instructions."""
        from papagai.markdown import MarkdownInstructions

        return MarkdownInstructions(text="Do something")

    def test_claude_run_creates_target_branch_if_not_exists(
        self, mock_repo, mock_instructions, tmp_path
    ):
        """Test claude_run creates target branch if it doesn't exist."""
        with patch("papagai.cli.get_branch") as mock_get_branch:
            with patch("papagai.cli.create_branch_if_not_exists") as mock_create:
                with patch("papagai.cli.Worktree.from_branch") as mock_worktree:
                    with patch("papagai.cli.run_claude"):
                        mock_get_branch.return_value = "main"
                        mock_create.return_value = "feature"

                        # Mock worktree context manager
                        mock_wt = MagicMock()
                        mock_wt.branch = "papagai/feature-123"
                        mock_wt.worktree_dir = tmp_path / "worktree"
                        mock_worktree.return_value.__enter__.return_value = mock_wt
                        mock_worktree.return_value.__exit__.return_value = None

                        # Need to patch cwd
                        with patch("papagai.cli.Path.cwd") as mock_cwd:
                            mock_cwd.return_value = mock_repo

                            from papagai.cli import claude_run

                            claude_run(
                                "main",
                                mock_instructions,
                                dry_run=False,
                                target_branch="feature",
                            )

                            # Should call create_branch_if_not_exists
                            mock_create.assert_called_once_with(
                                mock_repo, "feature", "main"
                            )

    def test_claude_run_uses_existing_target_branch(
        self, mock_repo, mock_instructions, tmp_path
    ):
        """Test claude_run uses existing target branch without creating."""
        with patch("papagai.cli.get_branch") as mock_get_branch:
            with patch("papagai.cli.create_branch_if_not_exists") as mock_create:
                with patch("papagai.cli.Worktree.from_branch") as mock_worktree:
                    with patch("papagai.cli.run_claude"):
                        mock_get_branch.return_value = "main"
                        mock_create.return_value = "existing-feature"

                        # Mock worktree context manager
                        mock_wt = MagicMock()
                        mock_wt.branch = "papagai/existing-feature-123"
                        mock_wt.worktree_dir = tmp_path / "worktree"
                        mock_worktree.return_value.__enter__.return_value = mock_wt
                        mock_worktree.return_value.__exit__.return_value = None

                        with patch("papagai.cli.Path.cwd") as mock_cwd:
                            mock_cwd.return_value = mock_repo

                            from papagai.cli import claude_run

                            claude_run(
                                "main",
                                mock_instructions,
                                dry_run=False,
                                target_branch="existing-feature",
                            )

                            mock_create.assert_called_once_with(
                                mock_repo, "existing-feature", "main"
                            )

    def test_claude_run_merges_work_into_target_branch(
        self, mock_repo, mock_instructions, tmp_path
    ):
        """Test claude_run merges worktree branch into target branch."""
        with patch("papagai.cli.get_branch") as mock_get_branch:
            with patch("papagai.cli.create_branch_if_not_exists") as mock_create:
                with patch("papagai.cli.Worktree.from_branch") as mock_worktree:
                    with patch(
                        "papagai.cli.WorktreeOverlayFs.from_branch"
                    ) as mock_overlay:
                        with patch("papagai.cli.run_claude"):
                            with patch(
                                "papagai.cli.merge_into_target_branch"
                            ) as mock_merge:
                                mock_get_branch.return_value = "main"
                                mock_create.return_value = "feature"
                                mock_merge.return_value = 0

                                # Mock worktree context manager
                                mock_wt = MagicMock()
                                mock_wt.branch = "papagai/feature-123"
                                mock_wt.worktree_dir = tmp_path / "worktree"
                                mock_worktree.return_value.__enter__.return_value = (
                                    mock_wt
                                )
                                mock_worktree.return_value.__exit__.return_value = None
                                mock_overlay.return_value.__enter__.return_value = (
                                    mock_wt
                                )
                                mock_overlay.return_value.__exit__.return_value = None

                                with patch("papagai.cli.Path.cwd") as mock_cwd:
                                    mock_cwd.return_value = mock_repo

                                    from papagai.cli import claude_run

                                    result = claude_run(
                                        "main",
                                        mock_instructions,
                                        dry_run=False,
                                        target_branch="feature",
                                    )

                                    # Should call merge_into_target_branch
                                    mock_merge.assert_called_once_with(
                                        mock_repo,
                                        dest="feature",
                                        src="papagai/feature-123",
                                    )
                                    assert result == 0

    def test_claude_run_returns_error_when_merge_fails(
        self, mock_repo, mock_instructions, tmp_path
    ):
        """Test claude_run returns error when merge fails."""
        with patch("papagai.cli.get_branch") as mock_get_branch:
            with patch("papagai.cli.create_branch_if_not_exists") as mock_create:
                with patch("papagai.cli.Worktree.from_branch") as mock_worktree:
                    with patch(
                        "papagai.cli.WorktreeOverlayFs.from_branch"
                    ) as mock_overlay:
                        with patch("papagai.cli.run_claude"):
                            with patch(
                                "papagai.cli.merge_into_target_branch"
                            ) as mock_merge:
                                mock_get_branch.return_value = "main"
                                mock_create.return_value = "feature"
                                mock_merge.return_value = 1  # Merge fails

                                # Mock worktree context manager
                                mock_wt = MagicMock()
                                mock_wt.branch = "papagai/feature-123"
                                mock_wt.worktree_dir = tmp_path / "worktree"
                                mock_worktree.return_value.__enter__.return_value = (
                                    mock_wt
                                )
                                mock_worktree.return_value.__exit__.return_value = None
                                mock_overlay.return_value.__enter__.return_value = (
                                    mock_wt
                                )
                                mock_overlay.return_value.__exit__.return_value = None

                                with patch("papagai.cli.Path.cwd") as mock_cwd:
                                    mock_cwd.return_value = mock_repo

                                    from papagai.cli import claude_run

                                    result = claude_run(
                                        "main",
                                        mock_instructions,
                                        dry_run=False,
                                        target_branch="feature",
                                    )

                                    assert result == 1

    def test_claude_run_without_target_branch_skips_merge(
        self, mock_repo, mock_instructions, tmp_path
    ):
        """Test claude_run without target_branch doesn't attempt merge."""
        with patch("papagai.cli.get_branch") as mock_get_branch:
            with patch("papagai.cli.create_branch_if_not_exists") as mock_create:
                with patch("papagai.cli.Worktree.from_branch") as mock_worktree:
                    with patch(
                        "papagai.cli.WorktreeOverlayFs.from_branch"
                    ) as mock_overlay:
                        with patch("papagai.cli.run_claude"):
                            with patch(
                                "papagai.cli.merge_into_target_branch"
                            ) as mock_merge:
                                mock_get_branch.return_value = "main"
                                mock_create.return_value = "main"

                                # Mock worktree context manager
                                mock_wt = MagicMock()
                                mock_wt.branch = "papagai/main-123"
                                mock_wt.worktree_dir = tmp_path / "worktree"
                                mock_worktree.return_value.__enter__.return_value = (
                                    mock_wt
                                )
                                mock_worktree.return_value.__exit__.return_value = None
                                mock_overlay.return_value.__enter__.return_value = (
                                    mock_wt
                                )
                                mock_overlay.return_value.__exit__.return_value = None

                                with patch("papagai.cli.Path.cwd") as mock_cwd:
                                    mock_cwd.return_value = mock_repo

                                    from papagai.cli import claude_run

                                    result = claude_run(
                                        "main",
                                        mock_instructions,
                                        dry_run=False,
                                        target_branch=None,  # No target branch
                                    )

                                    # Should NOT call merge
                                    mock_merge.assert_not_called()
                                    assert result == 0

    def test_claude_run_returns_error_when_branch_creation_fails(
        self, mock_repo, mock_instructions
    ):
        """Test claude_run returns error when target branch creation fails."""
        with patch("papagai.cli.get_branch") as mock_get_branch:
            with patch("papagai.cli.create_branch_if_not_exists") as mock_create:
                mock_get_branch.return_value = "main"
                mock_create.side_effect = subprocess.CalledProcessError(1, "git")

                with patch("papagai.cli.Path.cwd") as mock_cwd:
                    mock_cwd.return_value = mock_repo

                    from papagai.cli import claude_run

                    result = claude_run(
                        "main",
                        mock_instructions,
                        dry_run=False,
                        target_branch="feature",
                    )

                    assert result == 1
