# GitHub Integration Lite

Minimal GitHub integration skill with only 4 low-token-cost tools.

## Available Tools

1. `github_clone`
   - Purpose: Clone a GitHub repo into workspace
   - Params: `repo_url`, optional `target_dir`

2. `github_read_file`
   - Purpose: Read a file in the repo
   - Params: `repo_dir`, `file_path`

3. `github_commit_push`
   - Purpose: Run `git add/commit/push` in one call
   - Params: `repo_dir`, `message`, optional `branch`

4. `github_create_pr`
   - Purpose: Create a Pull Request
   - Params: `repo` (owner/name), `title`, `head`, optional `body`, `base`
   - Requirement: env var `GITHUB_TOKEN`

## Minimal Workflow

1. `github_clone` to fetch repo
2. `github_read_file` to inspect target files
3. Make edits, then call `github_commit_push`
4. Call `github_create_pr` to open PR

## Notes

- This skill is optimized for speed and stability with minimal context overhead.
- `github_create_pr` uses the GitHub REST API.
