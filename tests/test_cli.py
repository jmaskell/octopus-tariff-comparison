from datetime import date

import octopus_compare.cli as cli


def test_main_prints_report(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_load_env",
                        lambda: {"OCTOPUS_API_KEY": "sk", "OCTOPUS_ACCOUNT": "A-8F18337C"})
    monkeypatch.setattr(cli, "_today", lambda: date(2026, 4, 2))

    class FakeResult:
        pass

    monkeypatch.setattr(cli, "_build_client", lambda cfg: object())
    monkeypatch.setattr(cli, "run_comparison", lambda client, cfg: "RESULT")
    monkeypatch.setattr(cli, "format_text", lambda result: "REPORT-TEXT")

    code = cli.main(["--from", "2026-04-01", "--to", "2026-04-01"])
    assert code == 0
    assert "REPORT-TEXT" in capsys.readouterr().out


def test_main_config_error_returns_2(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_load_env", lambda: {})
    monkeypatch.setattr(cli, "_today", lambda: date(2026, 4, 2))
    code = cli.main([])
    assert code == 2
    assert "OCTOPUS_API_KEY" in capsys.readouterr().err
