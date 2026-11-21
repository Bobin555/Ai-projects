import pytest

import goldthread.cli as cli
from goldthread.extractor import ExtractReport
from goldthread.netguard import no_network


@pytest.fixture
def run(synthetic_pack, tmp_path, capsys):
    def _run(*args):
        code = cli.main(["--pack", str(synthetic_pack.root), "--data-root", str(tmp_path / "data"), *args])
        out, err = capsys.readouterr()
        return code, out, err
    return _run


def test_cli_pipeline_offline_under_no_network(run, synthetic_pack):
    with no_network():
        for args in (["ingest"], ["extract"], ["review-export"], ["ask", "What is the fuel temperature limit?"],
                     ["trace", "PDC 10"], ["check"], ["test"], ["spend"]):
            code, out, err = run(*args)
            assert code == 0, (args, out, err)
    data = synthetic_pack.data_dir
    assert list((data / "review").glob("review-*.csv"))
    assert list((data / "reports").glob("eval-*.md")) and (data / "ledger.sqlite3").is_file()


def test_cli_outputs(run):
    run("ingest")
    run("extract")
    code, out, _ = run("trace", "PDC 10")
    assert code == 0 and "cited, not available in this pack" in out
    code, out, _ = run("ask", "What is the fuel temperature limit?")
    assert code == 0 and "1650 C" in out
    code, out, err = run("check")
    assert "Requirements with no claim (1)" in out
    code, out, err = run("spend")
    assert code == 0 and "Cost summary" in out


def test_cli_fetch_offline_refused(run):
    code, out, err = run("fetch")
    assert code == 1 and "offline pack: fetch is disabled" in err


def test_cli_budget_stop_exit_3(run, monkeypatch):
    run("ingest")
    monkeypatch.setattr(cli, "extract_pack",
                        lambda *a, **k: ExtractReport("RUN-1", 5, 1, 0, 0, "budget: run limit", ["SYN-SE@r1#0"]))
    code, out, err = run("extract")
    assert code == 3 and "--resume RUN-1" in out + err and "run limit" in out + err


def test_cli_search_no_model_call(run, monkeypatch):
    run("ingest")

    def boom(*a, **k):
        raise AssertionError("search must not create a model connector")

    monkeypatch.setattr(cli, "get_connector", boom)
    code, out, _ = run("search", "fuel temperature limit")
    assert code == 0 and "SYN-SAR@r2#p1.1" in out


def test_cli_ask_html(run):
    run("ingest")
    code, out, _ = run("ask", "What is the fuel temperature limit?", "--html")
    assert code == 0 and out.startswith("<")


def test_cli_bad_pack_is_error(tmp_path, capsys):
    assert cli.main(["--pack", str(tmp_path / "missing"), "check"]) == 1
    assert "missing pack file" in capsys.readouterr().err


def test_cli_help_lists_commands(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    out = capsys.readouterr().out
    for command in ("fetch", "ingest", "search", "extract", "review-export", "review-import", "ask", "trace",
                    "check", "test", "spend"):
        assert command in out
