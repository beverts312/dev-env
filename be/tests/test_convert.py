import json

from click.testing import CliRunner

from be.cli import cli


def test_json_csv_writes_header_and_quotes(tmp_path):
    src = tmp_path / "data.json"
    src.write_text(json.dumps([{"a": 1, "b": "x, y"}, {"a": 2, "c": True}]))
    result = CliRunner().invoke(cli, ["convert", "json-csv", str(src)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "data.csv").read_text().splitlines() == [
        "a,b,c",
        '1,"x, y",',
        "2,,True",
    ]


def test_json_csv_to_stdout(tmp_path):
    src = tmp_path / "data.json"
    src.write_text(json.dumps([{"a": 1}]))
    result = CliRunner().invoke(cli, ["convert", "json-csv", str(src), "-o", "-"])
    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == ["a", "1"]
    assert not (tmp_path / "data.csv").exists()


def test_json_csv_rejects_non_array(tmp_path):
    src = tmp_path / "data.json"
    src.write_text(json.dumps({"a": 1}))
    result = CliRunner().invoke(cli, ["convert", "json-csv", str(src)])
    assert result.exit_code != 0
    assert "JSON array of objects" in result.output


def test_base64_round_trips(tmp_path):
    src = tmp_path / "blob.bin"
    src.write_bytes(b"hello\x00world")
    runner = CliRunner()
    encoded = runner.invoke(cli, ["convert", "base64", str(src)])
    assert encoded.output == "aGVsbG8Ad29ybGQ=\n"
    decoded = runner.invoke(cli, ["convert", "base64", "-d", "-"], input=encoded.output)
    assert decoded.stdout_bytes == b"hello\x00world"
