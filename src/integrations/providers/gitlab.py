from __future__ import annotations

from typing import Any

import requests

from src.integrations.base import IntegrationProvider, IntegrationResult, register_integration


@register_integration
class GitLabProvider(IntegrationProvider):
    name = "gitlab"
    description = "GitLab project and merge request management"
    icon = "gitlab"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.base_url = config.get("settings", {}).get("base_url", "https://gitlab.com/api/v4")
        token = self._credentials.get("token") or self._credentials.get("pat")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "AegisNex-Integration/1.0",
            }
        )
        if token:
            self.session.headers["PRIVATE-TOKEN"] = token

    async def health_check(self) -> dict[str, Any]:
        try:
            resp = self.session.get(f"{self.base_url}/projects?per_page=1", timeout=10)
            return {"status": "ok" if resp.ok else "error", "status_code": resp.status_code}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def execute(self, action: str, params: dict[str, Any]) -> IntegrationResult:
        handler = getattr(self, f"_action_{action}", None)
        if handler is None:
            return IntegrationResult(success=False, error=f"Unknown action: {action}")
        return self._timed(handler, params)

    def _action_list_projects(self, params: dict[str, Any]) -> Any:
        query_params = {
            "per_page": params.get("per_page", 30),
            "sort": params.get("sort", "updated_at"),
            "order_by": params.get("order_by", "updated_at"),
            "membership": params.get("membership", False),
        }
        if params.get("search"):
            query_params["search"] = params["search"]
        resp = self.session.get(f"{self.base_url}/projects", params=query_params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _action_create_issue(self, params: dict[str, Any]) -> Any:
        project_id = params.get("project_id")
        if not project_id:
            raise ValueError("project_id is required")
        data = {
            "title": params.get("title", ""),
            "description": params.get("description", ""),
            "labels": ",".join(params.get("labels", [])),
            "assignee_ids": params.get("assignee_ids", []),
        }
        resp = self.session.post(
            f"{self.base_url}/projects/{project_id}/issues", json=data, timeout=30
        )
        resp.raise_for_status()
        return resp.json()

    def _action_list_issues(self, params: dict[str, Any]) -> Any:
        project_id = params.get("project_id")
        if not project_id:
            raise ValueError("project_id is required")
        query_params = {
            "state": params.get("state", "opened"),
            "per_page": params.get("per_page", 30),
            "sort": params.get("sort", "updated_at"),
            "order_by": params.get("order_by", "updated_at"),
        }
        resp = self.session.get(
            f"{self.base_url}/projects/{project_id}/issues", params=query_params, timeout=30
        )
        resp.raise_for_status()
        return resp.json()

    def _action_get_commit(self, params: dict[str, Any]) -> Any:
        project_id = params.get("project_id")
        sha = params.get("sha")
        if not project_id or not sha:
            raise ValueError("project_id and sha are required")
        resp = self.session.get(
            f"{self.base_url}/projects/{project_id}/repository/commits/{sha}", timeout=30
        )
        resp.raise_for_status()
        return resp.json()

    def _action_list_mrs(self, params: dict[str, Any]) -> Any:
        project_id = params.get("project_id")
        if not project_id:
            raise ValueError("project_id is required")
        query_params = {
            "state": params.get("state", "opened"),
            "per_page": params.get("per_page", 30),
            "sort": params.get("sort", "updated_at"),
            "order_by": params.get("order_by", "updated_at"),
        }
        resp = self.session.get(
            f"{self.base_url}/projects/{project_id}/merge_requests", params=query_params, timeout=30
        )
        resp.raise_for_status()
        return resp.json()
