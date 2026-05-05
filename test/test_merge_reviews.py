#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for the merge-reviews command."""

import logging
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from papagai.cli import (
    BRANCH_PREFIX,
    find_review_branches,
    get_unique_commits,
    papagai,
    parse_relative_timestamp,
)

logger = logging.getLogger("papagai.test")


@pytest.fixture(autouse=True)
def mock_send_notification_for_tests():
    """Mock send_notification globally to avoid notification attempts in CLI tests."""
    with patch("papagai.cli.send_notification"):
        yield


@pytest.fixture
def real_git_repo(tmp_path):
    """Create a real git repository for integration tests."""
    repo_dir = tmp_path / "test-repo"
    repo_dir.mkdir()

    subprocess.run(
        ["git", "init", "-b", "main"],
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
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

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


def make_review_branch(
    repo_dir: Path,
    base_branch: str,
    date_str: str,
    uuid_str: str,
    files: dict[str, str],
    commit_messages: dict[str, str] | None = None,
) -> str:
    """Helper to create a review branch with specific commits.

    Args:
        repo_dir: Path to the git repo
        base_branch: Base branch to branch from
        date_str: Date string in YYYYmmdd-HHMM format
        uuid_str: UUID portion for branch name
        files: Dict of filename -> content to commit
        commit_messages: Optional dict of filename -> full commit message.
            If not provided, uses "Review fix: {filename}".

    Returns:
        The branch name created
    """
    branch_name = f"{BRANCH_PREFIX}/review/{base_branch}-{date_str}-{uuid_str}"

    subprocess.run(
        ["git", "branch", branch_name, base_branch],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    # Create a worktree to make commits on the branch
    worktree_dir = repo_dir / f"wt-{uuid_str}"
    subprocess.run(
        ["git", "worktree", "add", str(worktree_dir), branch_name],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    for filename, content in files.items():
        filepath = worktree_dir / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content)
        subprocess.run(
            ["git", "add", filename],
            cwd=worktree_dir,
            check=True,
            capture_output=True,
        )
        msg = (
            commit_messages.get(filename, f"Review fix: {filename}")
            if commit_messages
            else f"Review fix: {filename}"
        )
        subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=worktree_dir,
            check=True,
            capture_output=True,
        )

    # Clean up worktree
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(worktree_dir)],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )

    return branch_name


class TestParseRelativeTimestamp:
    """Tests for parse_relative_timestamp() function."""

    def test_parse_days(self):
        """Test parsing days."""
        before = datetime.now() - timedelta(days=2, seconds=1)
        result = parse_relative_timestamp("2d")
        after = datetime.now() - timedelta(days=2)
        assert before <= result <= after

    def test_parse_hours(self):
        """Test parsing hours."""
        before = datetime.now() - timedelta(hours=3, seconds=1)
        result = parse_relative_timestamp("3h")
        after = datetime.now() - timedelta(hours=3)
        assert before <= result <= after

    def test_parse_weeks(self):
        """Test parsing weeks."""
        before = datetime.now() - timedelta(weeks=1, seconds=1)
        result = parse_relative_timestamp("1w")
        after = datetime.now() - timedelta(weeks=1)
        assert before <= result <= after

    def test_parse_minutes(self):
        """Test parsing minutes."""
        before = datetime.now() - timedelta(minutes=30, seconds=1)
        result = parse_relative_timestamp("30m")
        after = datetime.now() - timedelta(minutes=30)
        assert before <= result <= after

    def test_parse_with_whitespace(self):
        """Test parsing with surrounding whitespace."""
        result = parse_relative_timestamp("  2d  ")
        expected_approx = datetime.now() - timedelta(days=2)
        assert abs((result - expected_approx).total_seconds()) < 2

    def test_invalid_format_no_unit(self):
        """Test that missing unit raises BadParameter."""
        import click

        with pytest.raises(click.BadParameter, match="Invalid relative timestamp"):
            parse_relative_timestamp("42")

    def test_invalid_format_no_number(self):
        """Test that missing number raises BadParameter."""
        import click

        with pytest.raises(click.BadParameter, match="Invalid relative timestamp"):
            parse_relative_timestamp("d")

    def test_invalid_format_unknown_unit(self):
        """Test that unknown unit raises BadParameter."""
        import click

        with pytest.raises(click.BadParameter, match="Invalid relative timestamp"):
            parse_relative_timestamp("2y")

    def test_invalid_format_empty(self):
        """Test that empty string raises BadParameter."""
        import click

        with pytest.raises(click.BadParameter, match="Invalid relative timestamp"):
            parse_relative_timestamp("")

    def test_invalid_format_garbage(self):
        """Test that garbage input raises BadParameter."""
        import click

        with pytest.raises(click.BadParameter, match="Invalid relative timestamp"):
            parse_relative_timestamp("yesterday")


class TestFindReviewBranches:
    """Tests for find_review_branches() function."""

    def test_finds_matching_branches(self, real_git_repo):
        """Test finding review branches for the current branch."""
        today = datetime.now().strftime("%Y%m%d-%H%M")

        make_review_branch(
            real_git_repo,
            "main",
            today,
            "aaa11111",
            {"fix1.txt": "fix 1\n"},
        )
        make_review_branch(
            real_git_repo,
            "main",
            today,
            "bbb22222",
            {"fix2.txt": "fix 2\n"},
        )

        since = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        branches = find_review_branches(real_git_repo, "main", since)

        assert len(branches) == 2
        assert all("papagai/review/main-" in b for b in branches)

    def test_filters_by_date(self, real_git_repo):
        """Test that branches before the since date are excluded."""
        today = datetime.now().strftime("%Y%m%d-%H%M")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d-%H%M")

        make_review_branch(
            real_git_repo,
            "main",
            yesterday,
            "old11111",
            {"old.txt": "old fix\n"},
        )
        make_review_branch(
            real_git_repo,
            "main",
            today,
            "new22222",
            {"new.txt": "new fix\n"},
        )

        # Only find today's branches
        since = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        branches = find_review_branches(real_git_repo, "main", since)

        assert len(branches) == 1
        assert "new22222" in branches[0]

    def test_no_matching_branches(self, real_git_repo):
        """Test when no review branches exist."""
        since = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        branches = find_review_branches(real_git_repo, "main", since)

        assert len(branches) == 0

    def test_filters_by_base_branch(self, real_git_repo):
        """Test that only branches for the specified base are found."""
        today = datetime.now().strftime("%Y%m%d-%H%M")

        # Create a branch for "main"
        make_review_branch(
            real_git_repo,
            "main",
            today,
            "main1111",
            {"main_fix.txt": "main fix\n"},
        )

        # Create a branch for "develop" (first create the develop branch)
        subprocess.run(
            ["git", "branch", "develop", "main"],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
        )
        make_review_branch(
            real_git_repo,
            "develop",
            today,
            "dev11111",
            {"dev_fix.txt": "dev fix\n"},
        )

        since = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        main_branches = find_review_branches(real_git_repo, "main", since)
        assert len(main_branches) == 1
        assert "main1111" in main_branches[0]

        dev_branches = find_review_branches(real_git_repo, "develop", since)
        assert len(dev_branches) == 1
        assert "dev11111" in dev_branches[0]

    def test_sorted_by_date_oldest_first(self, real_git_repo):
        """Test that branches are sorted oldest first."""
        now = datetime.now()
        earlier = (now - timedelta(hours=2)).strftime("%Y%m%d-%H%M")
        later = now.strftime("%Y%m%d-%H%M")

        make_review_branch(
            real_git_repo,
            "main",
            later,
            "lat11111",
            {"late.txt": "late fix\n"},
        )
        make_review_branch(
            real_git_repo,
            "main",
            earlier,
            "ear11111",
            {"early.txt": "early fix\n"},
        )

        since = now - timedelta(hours=3)
        branches = find_review_branches(real_git_repo, "main", since)

        assert len(branches) == 2
        # Earlier branch should come first
        assert "ear11111" in branches[0]
        assert "lat11111" in branches[1]

    def test_skips_unparseable_branch_names(self, real_git_repo):
        """Test that branches with invalid date formats are skipped."""
        # Create a branch with a non-standard naming pattern
        subprocess.run(
            ["git", "branch", f"{BRANCH_PREFIX}/review/main-baddate-aaa11111", "main"],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
        )

        since = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        branches = find_review_branches(real_git_repo, "main", since)
        assert len(branches) == 0


class TestGetUniqueCommits:
    """Tests for get_unique_commits() function."""

    def test_collects_commits_from_single_branch(self, real_git_repo):
        """Test collecting commits from a single review branch."""
        today = datetime.now().strftime("%Y%m%d-%H%M")
        branch = make_review_branch(
            real_git_repo,
            "main",
            today,
            "aaa11111",
            {"fix1.txt": "fix 1\n", "fix2.txt": "fix 2\n"},
        )

        commits = get_unique_commits(real_git_repo, [branch], "main")
        assert len(commits) == 2

    def test_deduplicates_identical_commits(self, real_git_repo):
        """Test that identical commits across branches are deduplicated."""
        today = datetime.now().strftime("%Y%m%d-%H%M")

        # Create two branches that both add the same file with the same content
        # and the same commit message
        branch1 = f"{BRANCH_PREFIX}/review/main-{today}-aaa11111"
        branch2 = f"{BRANCH_PREFIX}/review/main-{today}-bbb22222"

        for branch_name, uuid_str in [(branch1, "aaa11111"), (branch2, "bbb22222")]:
            subprocess.run(
                ["git", "branch", branch_name, "main"],
                cwd=real_git_repo,
                check=True,
                capture_output=True,
            )
            worktree_dir = real_git_repo / f"wt-{uuid_str}"
            subprocess.run(
                ["git", "worktree", "add", str(worktree_dir), branch_name],
                cwd=real_git_repo,
                check=True,
                capture_output=True,
            )
            filepath = worktree_dir / "same_fix.txt"
            filepath.write_text("identical fix content\n")
            subprocess.run(
                ["git", "add", "same_fix.txt"],
                cwd=worktree_dir,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "Review fix: same_fix.txt"],
                cwd=worktree_dir,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree_dir)],
                cwd=real_git_repo,
                check=True,
                capture_output=True,
            )

        commits = get_unique_commits(real_git_repo, [branch1, branch2], "main")
        # Should deduplicate: same patch means only one copy
        assert len(commits) == 1
        # The later branch's version should be kept
        assert commits[0][1] == branch2

    def test_keeps_unique_commits_from_multiple_branches(self, real_git_repo):
        """Test that different commits from different branches are all kept."""
        today = datetime.now().strftime("%Y%m%d-%H%M")

        branch1 = make_review_branch(
            real_git_repo,
            "main",
            today,
            "aaa11111",
            {"fix1.txt": "fix 1\n"},
        )
        branch2 = make_review_branch(
            real_git_repo,
            "main",
            today,
            "bbb22222",
            {"fix2.txt": "fix 2\n"},
        )

        commits = get_unique_commits(real_git_repo, [branch1, branch2], "main")
        assert len(commits) == 2

    def test_empty_branch_returns_no_commits(self, real_git_repo):
        """Test that branches with no commits beyond base return empty."""
        # Create a branch with no additional commits
        subprocess.run(
            [
                "git",
                "branch",
                f"{BRANCH_PREFIX}/review/main-20260505-0900-aaa11111",
                "main",
            ],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
        )

        commits = get_unique_commits(
            real_git_repo,
            [f"{BRANCH_PREFIX}/review/main-20260505-0900-aaa11111"],
            "main",
        )
        assert len(commits) == 0


class TestMergeReviewsCommand:
    """Tests for the merge-reviews CLI command."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_help(self, runner):
        """Test 'merge-reviews' command --help."""
        result = runner.invoke(papagai, ["merge-reviews", "--help"])
        assert result.exit_code == 0
        assert "Merge multiple papagai review branches" in result.output
        assert "--since" in result.output
        assert "--ref" in result.output

    def test_no_review_branches_found(self, runner, real_git_repo):
        """Test when no review branches exist."""
        with patch("papagai.cli.get_branch") as mock_get_branch:
            mock_get_branch.return_value = "main"
            with patch("papagai.cli.find_review_branches") as mock_find:
                mock_find.return_value = []

                result = runner.invoke(papagai, ["merge-reviews"])

                assert result.exit_code == 1
                assert "No review branches found" in result.output

    def test_invalid_since_flag(self, runner):
        """Test invalid --since value."""
        with patch("papagai.cli.get_branch") as mock_get_branch:
            mock_get_branch.return_value = "main"

            result = runner.invoke(papagai, ["merge-reviews", "--since", "invalid"])
            assert result.exit_code != 0

    def test_invalid_ref(self, runner):
        """Test with an invalid --ref."""
        with patch("papagai.cli.get_branch") as mock_get_branch:
            mock_get_branch.side_effect = subprocess.CalledProcessError(1, "git")

            result = runner.invoke(papagai, ["merge-reviews", "--ref", "nonexistent"])
            assert result.exit_code == 1
            assert "not a valid git reference" in result.output

    def test_merge_reviews_integration(self, real_git_repo):
        """Integration test: create review branches and merge them."""
        runner = CliRunner()
        today = datetime.now().strftime("%Y%m%d-%H%M")

        # Create two review branches with different fixes
        make_review_branch(
            real_git_repo,
            "main",
            today,
            "aaa11111",
            {"fix1.txt": "fix 1 content\n"},
        )
        make_review_branch(
            real_git_repo,
            "main",
            today,
            "bbb22222",
            {"fix2.txt": "fix 2 content\n"},
        )

        # Run merge-reviews from the repo directory
        with runner.isolated_filesystem(temp_dir=real_git_repo.parent):
            import os

            os.chdir(real_git_repo)

            result = runner.invoke(papagai, ["merge-reviews"])

            assert result.exit_code == 0, f"Output: {result.output}"
            assert "Found 2 review branch(es)" in result.output
            assert "Successfully merged" in result.output

        # Verify the merged branch was created
        branch_result = subprocess.run(
            [
                "git",
                "branch",
                "--format=%(refname:short)",
                "--list",
                f"{BRANCH_PREFIX}/merged-review/*",
            ],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        merged_branches = [b for b in branch_result.stdout.strip().split("\n") if b]
        assert len(merged_branches) == 1

        # Verify both fixes are in the merged branch
        merged_branch = merged_branches[0]
        for filename in ["fix1.txt", "fix2.txt"]:
            show_result = subprocess.run(
                ["git", "show", f"{merged_branch}:{filename}"],
                cwd=real_git_repo,
                check=True,
                capture_output=True,
                text=True,
            )
            assert show_result.returncode == 0

        # Verify papagai/latest was updated
        latest_result = subprocess.run(
            ["git", "rev-parse", f"{BRANCH_PREFIX}/latest"],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        merged_result = subprocess.run(
            ["git", "rev-parse", merged_branch],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        assert latest_result.stdout.strip() == merged_result.stdout.strip()

    def test_merge_reviews_with_since(self, real_git_repo):
        """Integration test: --since filters branches correctly."""
        runner = CliRunner()
        today = datetime.now().strftime("%Y%m%d-%H%M")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d-%H%M")

        # Create old and new review branches
        make_review_branch(
            real_git_repo,
            "main",
            yesterday,
            "old11111",
            {"old_fix.txt": "old fix\n"},
        )
        make_review_branch(
            real_git_repo,
            "main",
            today,
            "new22222",
            {"new_fix.txt": "new fix\n"},
        )

        with runner.isolated_filesystem(temp_dir=real_git_repo.parent):
            import os

            os.chdir(real_git_repo)

            # With default (today), should only find the new branch
            result = runner.invoke(papagai, ["merge-reviews"])
            assert result.exit_code == 0
            assert "Found 1 review branch(es)" in result.output

    def test_merge_reviews_with_since_includes_old(self, real_git_repo):
        """Integration test: --since 2d includes yesterday's branches."""
        runner = CliRunner()
        today = datetime.now().strftime("%Y%m%d-%H%M")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d-%H%M")

        make_review_branch(
            real_git_repo,
            "main",
            yesterday,
            "old11111",
            {"old_fix.txt": "old fix\n"},
        )
        make_review_branch(
            real_git_repo,
            "main",
            today,
            "new22222",
            {"new_fix.txt": "new fix\n"},
        )

        with runner.isolated_filesystem(temp_dir=real_git_repo.parent):
            import os

            os.chdir(real_git_repo)

            result = runner.invoke(papagai, ["merge-reviews", "--since", "2d"])
            assert result.exit_code == 0
            assert "Found 2 review branch(es)" in result.output

    def test_merge_reviews_with_conflicting_changes(self, real_git_repo):
        """Integration test: conflicting changes are resolved."""
        runner = CliRunner()
        today = datetime.now().strftime("%Y%m%d-%H%M")

        # Two branches modify the same file differently
        make_review_branch(
            real_git_repo,
            "main",
            today,
            "aaa11111",
            {"README.md": "# Modified by review 1\n"},
        )
        make_review_branch(
            real_git_repo,
            "main",
            today,
            "bbb22222",
            {"README.md": "# Modified by review 2\n"},
        )

        with runner.isolated_filesystem(temp_dir=real_git_repo.parent):
            import os

            os.chdir(real_git_repo)

            result = runner.invoke(papagai, ["merge-reviews"])
            assert result.exit_code == 0, f"Output: {result.output}"
            assert "Successfully merged" in result.output

        # Verify the merged branch has the later review's content
        # (since branches are sorted oldest-first, later branch wins)
        branch_result = subprocess.run(
            [
                "git",
                "branch",
                "--format=%(refname:short)",
                "--list",
                f"{BRANCH_PREFIX}/merged-review/*",
            ],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        merged_branch = branch_result.stdout.strip().split("\n")[0]
        show_result = subprocess.run(
            ["git", "show", f"{merged_branch}:README.md"],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        assert "Modified by review 2" in show_result.stdout

    def test_merge_reviews_worktree_cleanup(self, real_git_repo):
        """Integration test: worktree is cleaned up after merge."""
        runner = CliRunner()
        today = datetime.now().strftime("%Y%m%d-%H%M")

        make_review_branch(
            real_git_repo,
            "main",
            today,
            "aaa11111",
            {"fix1.txt": "fix\n"},
        )

        with runner.isolated_filesystem(temp_dir=real_git_repo.parent):
            import os

            os.chdir(real_git_repo)

            result = runner.invoke(papagai, ["merge-reviews"])
            assert result.exit_code == 0

        # Verify no worktrees are left behind
        wt_result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        # Should only have the main worktree
        worktree_count = wt_result.stdout.count("worktree ")
        assert worktree_count == 1

    def test_merge_reviews_does_not_disturb_checkout(self, real_git_repo):
        """Integration test: user's current checkout is not disturbed."""
        runner = CliRunner()
        today = datetime.now().strftime("%Y%m%d-%H%M")

        make_review_branch(
            real_git_repo,
            "main",
            today,
            "aaa11111",
            {"fix1.txt": "fix\n"},
        )

        with runner.isolated_filesystem(temp_dir=real_git_repo.parent):
            import os

            os.chdir(real_git_repo)

            # Get current branch before
            before = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=real_git_repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            result = runner.invoke(papagai, ["merge-reviews"])
            assert result.exit_code == 0

            # Get current branch after
            after = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=real_git_repo,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            assert before == after

    def test_merge_reviews_duplicate_commits_are_deduplicated(self, real_git_repo):
        """Integration test: identical patches across branches produce one commit."""
        runner = CliRunner()
        today = datetime.now().strftime("%Y%m%d-%H%M")

        # Create two branches with the exact same change
        for uuid_str in ["aaa11111", "bbb22222"]:
            branch_name = f"{BRANCH_PREFIX}/review/main-{today}-{uuid_str}"
            subprocess.run(
                ["git", "branch", branch_name, "main"],
                cwd=real_git_repo,
                check=True,
                capture_output=True,
            )
            worktree_dir = real_git_repo / f"wt-{uuid_str}"
            subprocess.run(
                ["git", "worktree", "add", str(worktree_dir), branch_name],
                cwd=real_git_repo,
                check=True,
                capture_output=True,
            )
            filepath = worktree_dir / "identical.txt"
            filepath.write_text("identical content\n")
            subprocess.run(
                ["git", "add", "identical.txt"],
                cwd=worktree_dir,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "Review fix: identical.txt"],
                cwd=worktree_dir,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree_dir)],
                cwd=real_git_repo,
                check=True,
                capture_output=True,
            )

        with runner.isolated_filesystem(temp_dir=real_git_repo.parent):
            import os

            os.chdir(real_git_repo)

            result = runner.invoke(papagai, ["merge-reviews"])
            assert result.exit_code == 0
            assert "1 unique commit(s)" in result.output
            assert "Successfully merged 1 commit(s)" in result.output

    def test_merge_reviews_preserves_full_commit_message(self, real_git_repo):
        """Integration test: full commit message (subject + body) is preserved."""
        runner = CliRunner()
        today = datetime.now().strftime("%Y%m%d-%H%M")

        commit_msg = (
            "Fix buffer overflow in input validation\n"
            "\n"
            "The input buffer was not bounds-checked before copying user data,\n"
            "which could lead to a heap overflow when processing untrusted input.\n"
            "\n"
            "This adds a length check before the memcpy call and returns an error\n"
            "if the input exceeds the maximum allowed size."
        )

        make_review_branch(
            real_git_repo,
            "main",
            today,
            "aaa11111",
            {"fix1.txt": "fixed content\n"},
            commit_messages={"fix1.txt": commit_msg},
        )

        with runner.isolated_filesystem(temp_dir=real_git_repo.parent):
            import os

            os.chdir(real_git_repo)

            result = runner.invoke(papagai, ["merge-reviews"])
            assert result.exit_code == 0

        # Find the merged branch and check its commit message
        branch_result = subprocess.run(
            [
                "git",
                "branch",
                "--format=%(refname:short)",
                "--list",
                f"{BRANCH_PREFIX}/merged-review/*",
            ],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        merged_branch = branch_result.stdout.strip().split("\n")[0]

        # Get the full commit message from the merged branch
        log_result = subprocess.run(
            ["git", "log", "--format=%B", "-1", merged_branch],
            cwd=real_git_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        merged_msg = log_result.stdout.strip()

        assert "Fix buffer overflow in input validation" in merged_msg
        assert "heap overflow when processing untrusted input" in merged_msg
        assert "adds a length check before the memcpy call" in merged_msg
