from __future__ import annotations

from typing import Any
from urllib.parse import quote

import requests

from src.integrations.base import IntegrationProvider, IntegrationResult, register_integration


@register_integration
class JiraProvider(IntegrationProvider):
    name = "jira"
    description = "Atlassian Jira issue and project management"
    icon = "jira"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.base_url = config.get("settings", {}).get("base_url", "").rstrip("/")
        if not self.base_url:
            raise ValueError("Jira base_url is required in settings")
        self.api_url = f"{self.base_url}/rest/api/3"
        token = self._credentials.get("token") or self._credentials.get("pat")
        username = self._credentials.get("username") or self._credentials.get("email")
        password = self._credentials.get("password") or self._credentials.get("api_token")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": "AegisNex-Integration/1.0",
            }
        )
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        elif username and password:
            self.session.auth = (username, password)

    async def health_check(self) -> dict[str, Any]:
        try:
            resp = self.session.get(f"{self.base_url}/rest/api/3/serverInfo", timeout=10)
            return {"status": "ok" if resp.ok else "error", "status_code": resp.status_code}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def execute(self, action: str, params: dict[str, Any]) -> IntegrationResult:
        handler = getattr(self, f"_action_{action}", None)
        if handler is None:
            return IntegrationResult(success=False, error=f"Unknown action: {action}")
        return self._timed(handler, params)

    def _action_create_issue(self, params: dict[str, Any]) -> Any:
        project_key = params.get("project_key")
        if not project_key:
            raise ValueError("project_key is required")
        data = {
            "fields": {
                "project": {"key": project_key},
                "summary": params.get("summary", ""),
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": params.get("description", "")}],
                        }
                    ],
                },
                "issuetype": {"name": params.get("issuetype", "Task")},
            }
        }
        if params.get("priority"):
            data["fields"]["priority"] = {"name": params["priority"]}
        if params.get("labels"):
            data["fields"]["labels"] = params["labels"]
        if params.get("assignee"):
            data["fields"]["assignee"] = {"id": params["assignee"]}
        resp = self.session.post(f"{self.api_url}/issue", json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _action_search_issues(self, params: dict[str, Any]) -> Any:
        jql = params.get("jql", "")
        if not jql:
            raise ValueError("jql query is required")
        query_params = {
            "jql": jql,
            "maxResults": params.get("max_results", 50),
            "startAt": params.get("start_at", 0),
            "fields": params.get("fields", "summary,status,assignee,priority,created"),
        }
        resp = self.session.get(f"{self.api_url}/search", params=query_params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _action_get_issue(self, params: dict[str, Any]) -> Any:
        issue_key = params.get("issue_key")
        if not issue_key:
            raise ValueError("issue_key is required")
        resp = self.session.get(f"{self.api_url}/issue/{quote(issue_key)}", timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _action_transition_issue(self, params: dict[str, Any]) -> Any:
        issue_key = params.get("issue_key")
        transition_id = params.get("transition_id")
        if not issue_key or not transition_id:
            raise ValueError("issue_key and transition_id are required")
        data = {"transition": {"id": transition_id}}
        resp = self.session.post(
            f"{self.api_url}/issue/{quote(issue_key)}/transitions", json=data, timeout=30
        )
        resp.raise_for_status()
        return resp.json()

    def _action_add_comment(self, params: dict[str, Any]) -> Any:
        issue_key = params.get("issue_key")
        body = params.get("body", "")
        if not issue_key:
            raise ValueError("issue_key is required")
        data = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": body}],
                    }
                ],
            }
        }
        resp = self.session.post(
            f"{self.api_url}/issue/{quote(issue_key)}/comment", json=data, timeout=30
        )
        resp.raise_for_status()
        return resp.json()
