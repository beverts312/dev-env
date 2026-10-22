"""Kubernetes troubleshooting helpers (ported from the bk CLI).

Auth uses the current kubeconfig context, as kubectl does.
"""

from __future__ import annotations

import base64
import subprocess
from typing import Any

import click

NODE_POOL_LABEL = "cloud.google.com/gke-nodepool"
DEFAULT_NAMESPACE = "default"
REMOVE_FINALIZERS_PATCH = '[ { "op": "remove", "path": "/metadata/finalizers" } ]'
EXTRA_HINT = "install be with the kube extra: uv tool install --editable './cli[kube]'"


def _kubernetes():
    try:
        import kubernetes
    except ImportError:
        raise click.ClickException(f"kubernetes is not installed; {EXTRA_HINT}") from None
    return kubernetes


def client():
    """A CoreV1Api for the current kubeconfig context."""
    kubernetes = _kubernetes()
    try:
        kubernetes.config.load_kube_config()
    except Exception as e:
        raise click.ClickException(f"failed to load kube config: {e}") from None
    return kubernetes.client.CoreV1Api()


def current_namespace() -> str:
    """The namespace of the current kubeconfig context, or default."""
    kubernetes = _kubernetes()
    try:
        _, context = kubernetes.config.list_kube_config_contexts()
    except Exception:
        return DEFAULT_NAMESPACE
    return (context or {}).get("context", {}).get("namespace") or DEFAULT_NAMESPACE


def pool_pods(api: Any, node_pool: str) -> list[Any]:
    """Every pod scheduled on a node in the GKE node pool."""
    nodes = api.list_node(label_selector=f"{NODE_POOL_LABEL}={node_pool}")
    pods = []
    for node in nodes.items:
        pods.extend(api.list_pod_for_all_namespaces(field_selector=f"spec.nodeName={node.metadata.name}").items)
    return pods


def ready_count(pod: Any) -> str:
    """Ready containers over total, like kubectl's READY column."""
    statuses = pod.status.container_statuses if pod.status else None
    if not statuses:
        return "N/A"
    return f"{sum(1 for s in statuses if s.ready)}/{len(statuses)}"


def decode_secret(secret: Any) -> dict[str, str]:
    """The secret's data with base64 values decoded."""
    return {
        key: base64.b64decode(value).decode("utf-8", errors="replace")
        for key, value in (secret.data or {}).items()
    }


def remove_finalizers(args: tuple[str, ...]) -> int:
    """Strip metadata.finalizers from the resource kubectl args select, via kubectl patch."""
    return _kubectl("patch", *args, "--type", "json", f"--patch={REMOVE_FINALIZERS_PATCH}").returncode


def get_all(args: tuple[str, ...]) -> int:
    """kubectl get every listable namespaced resource type, passing args to each get.

    Returns the last non-zero exit code, or 0 if every get succeeded.
    """
    types = _kubectl("api-resources", "--verbs=list", "--namespaced", "-o", "name", capture_output=True, text=True)
    if types.returncode:
        click.echo(types.stderr, err=True, nl=False)
        return types.returncode
    code = 0
    for name in types.stdout.split():
        code = _kubectl("get", name, "--show-kind", "--ignore-not-found", *args).returncode or code
    return code


def _kubectl(*args: str, **kwargs: Any) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["kubectl", *args], **kwargs)
    except FileNotFoundError:
        raise click.ClickException("kubectl is not installed or not on PATH") from None
