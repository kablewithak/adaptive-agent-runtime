from adaptive_runtime.cli import main


def test_main_emits_bootstrap_confirmation(capsys) -> None:
    result = main()

    captured = capsys.readouterr()

    assert result == 0
    assert captured.out == "adaptive-agent-runtime bootstrap OK\n"
