from piedgeai.config import load_config


def test_load_example_config():
    config = load_config("configs/models.example.json")
    assert config.server.port == 8080
    assert config.server.llama_binary.endswith("llama-cli")
    assert config.models["general"].path.endswith("qwen1_5b.gguf")
