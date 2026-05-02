# mcp/github/github_mcp.py

from github import Github
from typing import Optional, List
import os

class GitHubMCP:
    """
    GitHub MCP - 負責與 GitHub 互動
    """

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv("GITHUB_TOKEN")
        if not self.token:
            raise ValueError("請設定 GITHUB_TOKEN 環境變數")
        self.github = Github(self.token)
        self.user = self.github.get_user()

    def get_repo(self, repo_name: str):
        """取得指定 repository"""
        return self.github.get_repo(repo_name)

    def create_issue(self, repo_name: str, title: str, body: str = "", labels: List[str] = None):
        """建立 Issue"""
        repo = self.get_repo(repo_name)
        return repo.create_issue(title=title, body=body, labels=labels or [])

    def create_pull_request(self, repo_name: str, title: str, body: str, head: str, base: str = "main"):
        """建立 Pull Request"""
        repo = self.get_repo(repo_name)
        return repo.create_pull_request(title=title, body=body, head=head, base=base)

    def get_recent_commits(self, repo_name: str, limit: int = 10):
        """取得最近的 commit"""
        repo = self.get_repo(repo_name)
        return list(repo.get_commits()[:limit])

    def get_issues(self, repo_name: str, state: str = "open"):
        """取得 Issue 清單"""
        repo = self.get_repo(repo_name)
        return list(repo.get_issues(state=state))