from models import config


def test_persisted_grounding_disabled_wins_over_enabled_environment(
    tmp_path,
    monkeypatch,
):
    config_path = tmp_path / "model_config.json"
    config_path.write_text(
        '{"grounding":{"enabled":false}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("CREATOR_MODEL_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("WEB_GROUNDING_ENABLED", "1")
    config._clear_user_config_cache()

    try:
        assert config.get_web_grounding_enabled() is False
    finally:
        config._clear_user_config_cache()


def test_grounding_request_config_preserves_explicit_disabled(monkeypatch):
    monkeypatch.setenv("WEB_GROUNDING_ENABLED", "1")
    token = config.set_request_tool_configs(
        {
            config.CREATOR_GROUNDING_CONFIG_TOOL: {
                "enabled": False,
                "reuse_llm": True,
            },
        },
    )
    try:
        assert config.get_web_grounding_enabled() is False
    finally:
        config.reset_request_tool_configs(token)


def test_grounding_reuses_creator_llm_by_default(monkeypatch):
    monkeypatch.setattr(config, "get_text_api_key", lambda: "llm-key")
    monkeypatch.setattr(
        config,
        "get_text_base_url",
        lambda: "https://llm.example.test/v1",
    )
    monkeypatch.setattr(config, "get_text_model_name", lambda: "qwen-test")
    token = config.set_request_tool_configs(
        {
            config.CREATOR_GROUNDING_CONFIG_TOOL: {
                "enabled": True,
                "reuse_llm": True,
            },
        },
    )
    try:
        assert config.get_web_grounding_model_api_key() == "llm-key"
        assert (
            config.get_web_grounding_model_base_url()
            == "https://llm.example.test/v1"
        )
        assert config.get_web_grounding_model_name() == "qwen-test"
    finally:
        config.reset_request_tool_configs(token)


def test_grounding_can_override_creator_llm():
    token = config.set_request_tool_configs(
        {
            config.CREATOR_GROUNDING_CONFIG_TOOL: {
                "enabled": True,
                "reuse_llm": False,
                "api_key": "grounding-key",
                "base_url": "https://grounding.example.test/v1",
                "model": "grounding-qwen",
            },
        },
    )
    try:
        assert config.get_web_grounding_model_api_key() == "grounding-key"
        assert (
            config.get_web_grounding_model_base_url()
            == "https://grounding.example.test/v1"
        )
        assert config.get_web_grounding_model_name() == "grounding-qwen"
    finally:
        config.reset_request_tool_configs(token)


def test_grounding_search_and_validation_models_are_independent(monkeypatch):
    monkeypatch.setattr(config, "get_vlm_api_key", lambda: "verifier-key")
    monkeypatch.setattr(
        config,
        "get_vlm_base_url",
        lambda: "https://vision.example.test/v1",
    )
    monkeypatch.setattr(config, "get_vlm_model_name", lambda: "generic-vlm")
    token = config.set_request_tool_configs(
        {
            config.CREATOR_GROUNDING_CONFIG_TOOL: {
                "enabled": True,
                "validation_source": "vlm",
                "search_reuse_llm": False,
                "search_api_key": "search-key",
                "search_base_url": (
                    "https://dashscope.aliyuncs.com/compatible-mode/v1"
                ),
                "search_model": "qwen3.7-plus",
                "search_protocol": "DashScope（百炼）",
            },
        },
    )
    try:
        assert config.get_web_grounding_model_api_key() == "verifier-key"
        assert config.get_web_grounding_model_name() == "generic-vlm"
        assert config.get_web_grounding_search_api_key() == "search-key"
        assert config.get_web_grounding_search_model_name() == "qwen3.7-plus"
    finally:
        config.reset_request_tool_configs(token)
