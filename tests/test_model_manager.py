from piedgeai.config import ModelConfig, ServerConfig
from piedgeai.model_manager import ModelManager


def test_builds_llama_cli_command_from_existing_pi_layout():
    manager = ModelManager(ServerConfig(llama_binary="/home/pi/llama.cpp/build/bin/llama-cli"), {})
    model = ModelConfig(
        key="general",
        name="Qwen",
        path="/home/pi/llama.cpp/models/qwen1_5b.gguf",
        llama_args=["-c", "64"],
        defaults={"temperature": 0.4, "top_p": 0.8, "max_tokens": 128},
    )

    command = manager._build_command(model, "hello", {})

    assert command[:5] == [
        "/home/pi/llama.cpp/build/bin/llama-cli",
        "-m",
        "/home/pi/llama.cpp/models/qwen1_5b.gguf",
        "-p",
        "hello",
    ]
    assert ["-c", "64"] == command[5:7]
    assert ["-n", "128"] == command[7:9]
    assert ["--temp", "0.4"] == command[9:11]
    assert ["--top-p", "0.8"] == command[11:13]
