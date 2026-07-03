from __future__ import annotations

import json
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from src.integrations.base import IntegrationProvider, IntegrationResult, register_integration


@register_integration
class KubernetesProvider(IntegrationProvider):
    name = "kubernetes"
    description = "Kubernetes cluster management and monitoring"
    icon = "kubernetes"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self.kubeconfig = config.get("settings", {}).get("kubeconfig", "")
        self.context = config.get("settings", {}).get("context", "")
        self.in_cluster = config.get("settings", {}).get("in_cluster", False)
        self._k8s_client = None
        self._use_kubectl = config.get("settings", {}).get("use_kubectl", False)

    def _get_kubectl_cmd(self) -> List[str]:
        cmd = ["kubectl"]
        if self.kubeconfig:
            cmd.extend(["--kubeconfig", self.kubeconfig])
        if self.context:
            cmd.extend(["--context", self.context])
        return cmd

    def _run_kubectl(self, args: List[str]) -> Any:
        cmd = self._get_kubectl_cmd() + args
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise RuntimeError(f"kubectl error: {result.stderr.strip()}")
        if result.stdout.strip():
            return json.loads(result.stdout)
        return {}

    async def health_check(self) -> Dict[str, Any]:
        try:
            if self._use_kubectl:
                result = subprocess.run(
                    self._get_kubectl_cmd() + ["cluster-info", "--request-timeout=5s"],
                    capture_output=True, text=True, timeout=10,
                )
                return {"status": "ok" if result.returncode == 0 else "error", "output": result.stdout.strip()}
            import kubernetes
            kubernetes.config.load_incluster_config()
            v1 = kubernetes.client.CoreV1Api()
            v1.get_api_resources()
            return {"status": "ok"}
        except ImportError:
            try:
                return await self.health_check()
            except Exception as e:
                return {"status": "error", "error": str(e)}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def execute(self, action: str, params: Dict[str, Any]) -> IntegrationResult:
        handler = getattr(self, f"_action_{action}", None)
        if handler is None:
            return IntegrationResult(success=False, error=f"Unknown action: {action}")
        return self._timed(handler, params)

    def _try_k8s_client(self, method: str, *args, **kwargs) -> Any:
        if self._use_kubectl:
            raise ImportError("use_kubectl is set")
        try:
            import kubernetes
            if self.in_cluster:
                kubernetes.config.load_incluster_config()
            else:
                kubernetes.config.load_kube_config(
                    config_file=self.kubeconfig or None,
                    context=self.context or None,
                )
            client = getattr(kubernetes.client, f"{method}Api")()
            return getattr(client, kwargs.pop("api_method"))(*args, **kwargs)
        except ImportError:
            raise ImportError("kubernetes Python package not available, set use_kubectl=true or install kubernetes")

    def _action_list_pods(self, params: Dict[str, Any]) -> Any:
        namespace = params.get("namespace", "default")
        label_selector = params.get("label_selector", "")
        try:
            v1 = self._try_k8s_client("CoreV1", api_method="list_namespaced_pod")
            pods = v1.list_namespaced_pod(namespace, label_selector=label_selector)
            return [{"name": p.metadata.name, "namespace": p.metadata.namespace,
                      "status": p.status.phase, "node": p.spec.node_name,
                      "ip": p.status.pod_ip, "created": str(p.metadata.creation_timestamp)} for p in pods.items]
        except ImportError:
            args = ["get", "pods", "-n", namespace, "-o", "json"]
            if label_selector:
                args.extend(["-l", label_selector])
            data = self._run_kubectl(args)
            items = []
            for item in data.get("items", []):
                items.append({
                    "name": item["metadata"]["name"],
                    "namespace": item["metadata"]["namespace"],
                    "status": item["status"]["phase"],
                    "node": item["spec"].get("nodeName", ""),
                    "ip": item["status"].get("podIP", ""),
                    "created": item["metadata"].get("creationTimestamp", ""),
                })
            return items

    def _action_get_pod_logs(self, params: Dict[str, Any]) -> Any:
        namespace = params.get("namespace", "default")
        pod_name = params.get("pod_name")
        if not pod_name:
            raise ValueError("pod_name is required")
        container = params.get("container", "")
        tail_lines = params.get("tail_lines", 100)
        try:
            v1 = self._try_k8s_client("CoreV1", api_method="read_namespaced_pod_log")
            log = v1.read_namespaced_pod_log(pod_name, namespace, container=container or None, tail_lines=tail_lines)
            return log
        except ImportError:
            args = ["logs", pod_name, "-n", namespace, f"--tail={tail_lines}", "--output=json"]
            if container:
                args.extend(["-c", container])
            return self._run_kubectl(args)

    def _action_get_deployments(self, params: Dict[str, Any]) -> Any:
        namespace = params.get("namespace", "default")
        try:
            apps = self._try_k8s_client("AppsV1", api_method="list_namespaced_deployment")
            deps = apps.list_namespaced_deployment(namespace)
            return [{"name": d.metadata.name, "namespace": d.metadata.namespace,
                      "replicas": d.spec.replicas, "ready": d.status.ready_replicas or 0,
                      "created": str(d.metadata.creation_timestamp)} for d in deps.items]
        except ImportError:
            data = self._run_kubectl(["get", "deployments", "-n", namespace, "-o", "json"])
            items = []
            for item in data.get("items", []):
                items.append({
                    "name": item["metadata"]["name"],
                    "namespace": item["metadata"]["namespace"],
                    "replicas": item["spec"].get("replicas", 0),
                    "ready": item["status"].get("readyReplicas", 0),
                    "created": item["metadata"].get("creationTimestamp", ""),
                })
            return items

    def _action_get_services(self, params: Dict[str, Any]) -> Any:
        namespace = params.get("namespace", "default")
        try:
            v1 = self._try_k8s_client("CoreV1", api_method="list_namespaced_service")
            svcs = v1.list_namespaced_service(namespace)
            return [{"name": s.metadata.name, "namespace": s.metadata.namespace,
                      "type": s.spec.type, "cluster_ip": s.spec.cluster_ip,
                      "ports": [{"port": p.port, "target_port": str(p.target_port or "")} for p in (s.spec.ports or [])],
                      "created": str(s.metadata.creation_timestamp)} for s in svcs.items]
        except ImportError:
            data = self._run_kubectl(["get", "services", "-n", namespace, "-o", "json"])
            items = []
            for item in data.get("items", []):
                ports = []
                for p in item["spec"].get("ports", []):
                    ports.append({"port": p["port"], "target_port": str(p.get("targetPort", ""))})
                items.append({
                    "name": item["metadata"]["name"],
                    "namespace": item["metadata"]["namespace"],
                    "type": item["spec"]["type"],
                    "cluster_ip": item["spec"].get("clusterIP", ""),
                    "ports": ports,
                    "created": item["metadata"].get("creationTimestamp", ""),
                })
            return items

    def _action_get_nodes(self, params: Dict[str, Any]) -> Any:
        try:
            v1 = self._try_k8s_client("CoreV1", api_method="list_node")
            nodes = v1.list_node()
            return [{"name": n.metadata.name, "status": n.status.conditions[-1].type if n.status.conditions else "Unknown",
                      "kubelet": n.status.node_info.kubelet_version if n.status.node_info else "",
                      "os": n.status.node_info.os_image if n.status.node_info else "",
                      "created": str(n.metadata.creation_timestamp)} for n in nodes.items]
        except ImportError:
            data = self._run_kubectl(["get", "nodes", "-o", "json"])
            items = []
            for item in data.get("items", []):
                conditions = item["status"].get("conditions", [])
                status = conditions[-1]["type"] if conditions else "Unknown"
                node_info = item["status"].get("nodeInfo", {})
                items.append({
                    "name": item["metadata"]["name"],
                    "status": status,
                    "kubelet": node_info.get("kubeletVersion", ""),
                    "os": node_info.get("osImage", ""),
                    "created": item["metadata"].get("creationTimestamp", ""),
                })
            return items

    def _action_restart_deployment(self, params: Dict[str, Any]) -> Any:
        namespace = params.get("namespace", "default")
        deployment_name = params.get("deployment_name")
        if not deployment_name:
            raise ValueError("deployment_name is required")
        try:
            apps = self._try_k8s_client("AppsV1", api_method="patch_namespaced_deployment")
            body = {"spec": {"template": {"metadata": {"annotations": {"kubectl.kubernetes.io/restartedAt": datetime.utcnow().isoformat() + "Z"}}}}}
            apps.patch_namespaced_deployment(deployment_name, namespace, body)
            return {"status": "restarted", "deployment": deployment_name}
        except ImportError:
            result = subprocess.run(
                self._get_kubectl_cmd() + ["rollout", "restart", f"deployment/{deployment_name}", "-n", namespace],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                raise RuntimeError(f"rollout restart failed: {result.stderr.strip()}")
            return {"status": "restarted", "deployment": deployment_name, "output": result.stdout.strip()}
