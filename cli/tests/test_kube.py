import base64
import builtins
from types import SimpleNamespace as NS

import pytest
from click.testing import CliRunner

from be import kube as lib
from be.cli import cli


def pod(name, namespace, ready=None):
    statuses = None if ready is None else [NS(ready=r) for r in ready]
    return NS(metadata=NS(name=name, namespace=namespace), status=NS(container_statuses=statuses))


class FakeApi:
    def __init__(self, nodes=(), pods=None, secret=None):
        self.nodes = nodes
        self.pods = pods or {}
        self.secret = secret
        self.calls = []

    def list_node(self, label_selector):
        self.calls.append(("list_node", label_selector))
        return NS(items=[NS(metadata=NS(name=n)) for n in self.nodes])

    def list_pod_for_all_namespaces(self, field_selector):
        self.calls.append(("list_pods", field_selector))
        node = field_selector.removeprefix("spec.nodeName=")
        return NS(items=self.pods.get(node, []))

    def read_namespaced_secret(self, name, namespace):
        self.calls.append(("read_secret", name, namespace))
        if self.secret is None:
            raise type("ApiException", (Exception,), {"status": 404})()
        return self.secret


@pytest.mark.parametrize(
    ("ready", "expected"),
    [(None, "N/A"), ([], "N/A"), ([True], "1/1"), ([True, False, True], "2/3")],
)
def test_ready_count(ready, expected):
    assert lib.ready_count(pod("p", "ns", ready)) == expected


def test_decode_secret_handles_empty_data():
    assert lib.decode_secret(NS(data=None)) == {}
    assert lib.decode_secret(NS(data={"k": base64.b64encode(b"v").decode()})) == {"k": "v"}


def test_pool_pods_spans_nodes():
    api = FakeApi(nodes=["n1", "n2"], pods={"n1": [pod("a", "x")], "n2": [pod("b", "y")]})
    assert [p.metadata.name for p in lib.pool_pods(api, "web")] == ["a", "b"]
    assert api.calls[0] == ("list_node", "cloud.google.com/gke-nodepool=web")


def test_pool_command(monkeypatch):
    pytest.importorskip("rich")
    api = FakeApi(nodes=["n1"], pods={"n1": [pod("api-123", "prod", [True, True])]})
    monkeypatch.setattr(lib, "client", lambda: api)
    result = CliRunner().invoke(cli, ["kube", "pool", "web"], env={"COLUMNS": "200"})
    assert result.exit_code == 0, result.output
    assert "api-123" in result.output
    assert "prod" in result.output
    assert "2/2" in result.output


def test_secret_command_uses_current_namespace(monkeypatch):
    pytest.importorskip("rich")
    api = FakeApi(secret=NS(data={"password": base64.b64encode(b"hunter2").decode()}))
    monkeypatch.setattr(lib, "client", lambda: api)
    monkeypatch.setattr(lib, "current_namespace", lambda: "team")
    result = CliRunner().invoke(cli, ["kube", "secret", "db"], env={"COLUMNS": "200"})
    assert result.exit_code == 0, result.output
    assert "hunter2" in result.output
    assert api.calls == [("read_secret", "db", "team")]


def test_secret_command_not_found(monkeypatch):
    pytest.importorskip("rich")
    monkeypatch.setattr(lib, "client", lambda: FakeApi())
    result = CliRunner().invoke(cli, ["kube", "secret", "db", "-n", "prod"])
    assert result.exit_code == 1
    assert "secret db not found in namespace prod" in result.output


def test_missing_extra_hint(monkeypatch):
    real_import = builtins.__import__

    def no_kubernetes(name, *args, **kwargs):
        if name == "kubernetes":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_kubernetes)
    with pytest.raises(Exception, match=r"cli\[kube\]"):
        lib.client()


def test_rm_fin_command_passes_args_to_kubectl(monkeypatch):
    calls = []
    monkeypatch.setattr(lib.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or NS(returncode=0))
    result = CliRunner().invoke(cli, ["kube", "rm-fin", "pod", "foo", "-n", "prod"])
    assert result.exit_code == 0, result.output
    assert calls == [
        ["kubectl", "patch", "pod", "foo", "-n", "prod", "--type", "json", f"--patch={lib.REMOVE_FINALIZERS_PATCH}"]
    ]


def test_rm_fin_command_propagates_failure(monkeypatch):
    monkeypatch.setattr(lib.subprocess, "run", lambda cmd, **kw: NS(returncode=1))
    result = CliRunner().invoke(cli, ["kube", "rm-fin", "pod/foo"])
    assert result.exit_code == 1


def test_rm_fin_requires_resource():
    result = CliRunner().invoke(cli, ["kube", "rm-fin"])
    assert result.exit_code == 2


def test_get_all_command_gets_each_type(monkeypatch):
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        if cmd[1] == "api-resources":
            return NS(returncode=0, stdout="pods\nsecrets\n", stderr="")
        return NS(returncode=1 if cmd[2] == "pods" else 0)

    monkeypatch.setattr(lib.subprocess, "run", run)
    result = CliRunner().invoke(cli, ["kube", "get-all", "-n", "prod"])
    assert result.exit_code == 1
    assert calls[1:] == [
        ["kubectl", "get", "pods", "--show-kind", "--ignore-not-found", "-n", "prod"],
        ["kubectl", "get", "secrets", "--show-kind", "--ignore-not-found", "-n", "prod"],
    ]


def test_get_all_command_stops_when_api_resources_fails(monkeypatch):
    calls = []
    monkeypatch.setattr(
        lib.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or NS(returncode=1, stdout="", stderr="no cluster\n")
    )
    result = CliRunner().invoke(cli, ["kube", "get-all"])
    assert result.exit_code == 1
    assert len(calls) == 1
