---
allowed-tools: Bash(git add:*), Bash(git status:*), Bash(git diff:*), Bash(git log:*), Bash(git commit:*), Bash(git push:*)
description: Commit changes and push to remote
---

## Context

- Current git status: !`git status`
- Current git diff (staged and unstaged changes): !`git diff HEAD`
- Current branch: !`git branch --show-current`
- Recent commits: !`git log --oneline -10`

## Rules

1. **Author**: The commit author must ALWAYS be the user. NEVER add "Co-Authored-By: Claude" or any Claude attribution to commit messages. Claude is not a co-author.
2. **Atomic commits**: If there are changes across multiple unrelated areas (e.g. different features, different files serving different purposes), split them into multiple focused commits. Each commit should be a single logical change. If all changes are related, use a single commit.
3. **Push**: Always push to remote after committing.
4. **Commit messages**: Keep them concise (1-2 sentences). Match the style of recent commits in the repo. Use a HEREDOC to pass the message.
5. **Secrets**: Never commit files that contain secrets (.env, credentials, API keys). Warn the user if staged.
6. **Staging**: Prefer adding specific files by name rather than `git add -A` or `git add .`.

## Your task

Based on the above changes, create the appropriate commit(s) and push to remote.

Stage files, create commit(s), and push using tool calls. Do not send any other text or messages besides these tool calls.
