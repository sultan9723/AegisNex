from __future__ import annotations

from typing import Any

import requests

from src.integrations.base import IntegrationProvider, IntegrationResult, register_integration


@register_integration
class GitHubProvider(IntegrationProvider):
    name = "github"
    description = "GitHub repository and issue management"
    icon = "github"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.base_url = config.get("settings", {}).get("base_url", "https://api.github.com")
        token = self._credentials.get("token") or self._credentials.get("pat")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "AegisNex-Integration/1.0",
            }
        )
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    async def health_check(self) -> dict[str, Any]:
        try:
            resp = self.session.get(f"{self.base_url}", timeout=10)
            return {"status": "ok" if resp.ok else "error", "status_code": resp.status_code}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def execute(self, action: str, params: dict[str, Any]) -> IntegrationResult:
        handler = getattr(self, f"_action_{action}", None)
        if handler is None:
            return IntegrationResult(success=False, error=f"Unknown action: {action}")
        return self._timed(handler, params)

    def _action_list_repos(self, params: dict[str, Any]) -> Any:
        username = params.get("username", "")
        url = (
            f"{self.base_url}/users/{username}/repos" if username else f"{self.base_url}/user/repos"
        )
        resp = self.session.get(
            url,
            params={"per_page": params.get("per_page", 30), "sort": params.get("sort", "updated")},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def _action_create_issue(self, params: dict[str, Any]) -> Any:
        owner = params.get("owner")
        repo = params.get("repo")
        if not owner or not repo:
            raise ValueError("owner and repo are required")
        data = {
            "title": params.get("title", ""),
            "body": params.get("body", ""),
            "labels": params.get("labels", []),
            "assignees": params.get("assignees", []),
        }
        resp = self.session.post(
            f"{self.base_url}/repos/{owner}/{repo}/issues", json=data, timeout=30
        )
        resp.raise_for_status()
        return resp.json()

    def _action_list_issues(self, params: dict[str, Any]) -> Any:
        owner = params.get("owner")
        repo = params.get("repo")
        if not owner or not repo:
            raise ValueError("owner and repo are required")
        query_params = {
            "state": params.get("state", "open"),
            "per_page": params.get("per_page", 30),
            "sort": params.get("sort", "updated"),
            "direction": params.get("direction", "desc"),
        }
        resp = self.session.get(
            f"{self.base_url}/repos/{owner}/{repo}/issues", params=query_params, timeout=30
        )
        resp.raise_for_status()
        return resp.json()

    def _action_get_commit(self, params: dict[str, Any]) -> Any:
        owner = params.get("owner")
        repo = params.get("repo")
        sha = params.get("sha")
        if not owner or not repo or not sha:
            raise ValueError("owner, repo, and sha are required")
        resp = self.session.get(f"{self.base_url}/repos/{owner}/{repo}/commits/{sha}", timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _action_list_prs(self, params: dict[str, Any]) -> Any:
        owner = params.get("owner")
        repo = params.get("repo")
        if not owner or not repo:
            raise ValueError("owner and repo are required")
        query_params = {
            "state": params.get("state", "open"),
            "per_page": params.get("per_page", 30),
            "sort": params.get("sort", "updated"),
            "direction": params.get("direction", "desc"),
        }
        resp = self.session.get(
            f"{self.base_url}/repos/{owner}/{repo}/pulls", params=query_params, timeout=30
        )
        resp.raise_for_status()
        return resp.json()
