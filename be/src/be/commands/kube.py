"""`be kube`: Kubernetes troubleshooting helpers (ported from bk)."""

from __future__ import annotations

import click

from be import kube as lib


def _console():
    try:
        from rich.console import Console
        from rich.table import Table
    except ImportError:
        raise click.ClickException(f"rich is not installed; {lib.EXTRA_HINT}") from None
    return Console(), Table


@click.group()
def kube() -> None:
    """Kubernetes troubleshooting helpers, using the current kubeconfig context."""


@kube.command()
@click.argument("node_pool")
def pool(node_pool: str) -> None:
    """List the pods on every node in the GKE node pool NODE_POOL."""
    console, Table = _console()
    pods = lib.pool_pods(lib.client(), node_pool)
    table = Table(title=f"Pods in node pool {node_pool}")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Namespace", style="magenta", no_wrap=True)
    table.add_column("Ready", style="magenta", no_wrap=True)
    for pod in pods:
        table.add_row(pod.metadata.name, pod.metadata.namespace, lib.ready_count(pod))
    console.print(table)


@kube.command()
@click.argument("name")
@click.option("-n", "--namespace", help="Namespace (default: the current context's namespace).")
def secret(name: str, namespace: str | None) -> None:
    """Print secret NAME with its values base64-decoded."""
    console, Table = _console()
    api = lib.client()
    namespace = namespace or lib.current_namespace()
    try:
        data = lib.decode_secret(api.read_namespaced_secret(name, namespace))
    except Exception as e:
        if getattr(e, "status", None) == 404:
            raise click.ClickException(f"secret {name} not found in namespace {namespace}") from None
        raise
    table = Table(title=f"Secret {name} in namespace {namespace}")
    table.add_column("Key", style="cyan", no_wrap=True)
    table.add_column("Value", style="magenta")
    for key, value in data.items():
        table.add_row(key, value)
    console.print(table)


@kube.command("rm-fin", context_settings={"ignore_unknown_options": True})
@click.argument("resource", nargs=-1, required=True, type=click.UNPROCESSED)
def rm_fin(resource: tuple[str, ...]) -> None:
    """Remove the finalizers from RESOURCE (e.g. pod/foo or pod foo -n ns), so a stuck delete can finish.

    Arguments go straight to kubectl patch, so any resource type and kubectl flag works.
    """
    code = lib.remove_finalizers(resource)
    if code:
        raise SystemExit(code)


@kube.command("get-all", context_settings={"ignore_unknown_options": True})
@click.argument("kubectl_args", nargs=-1, type=click.UNPROCESSED)
def get_all(kubectl_args: tuple[str, ...]) -> None:
    """List every resource of every namespaced type (kubectl get for each api-resource).

    Extra arguments, such as -n ns or -l app=foo, go to each kubectl get.
    """
    code = lib.get_all(kubectl_args)
    if code:
        raise SystemExit(code)
