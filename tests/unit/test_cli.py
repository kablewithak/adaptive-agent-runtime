from pathlib import Path

from adaptive_runtime.cli import main
from adaptive_runtime.contracts.config import load_account_config


def test_configure_profile_writes_nonsecret_local_config(tmp_path: Path) -> None:
    config_path = tmp_path / "account.local.json"

    result = main(
        (
            "configure-profile",
            "--config",
            str(config_path),
            "--profile",
            "primary-openai",
            "--endpoint",
            ("https://api-ap-southeast-1.modelarts-maas.com/openai/v1/chat/completions"),
            "--region",
            "console-region",
            "--model",
            "glm-5.1",
        )
    )

    assert result == 0

    config = load_account_config(config_path)
    assert config.profiles[0].profile_name == "primary-openai"
    assert config.profiles[0].model_id == "glm-5.1"
    assert "api_key" not in config_path.read_text(encoding="utf-8").lower()
