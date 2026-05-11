from piedgeai.router import TaskRouter


def test_routes_code_prompt_to_code_model():
    router = TaskRouter({"general", "code", "utility"})
    decision = router.route("Please debug this Python traceback")
    assert decision.model_key == "code"


def test_routes_utility_prompt_to_utility_model():
    router = TaskRouter({"general", "code", "utility"})
    decision = router.route("Summarize this log in three bullets")
    assert decision.model_key == "utility"


def test_falls_back_to_general_for_chat():
    router = TaskRouter({"general", "code", "utility"})
    decision = router.route("How should I plan my edge runtime?")
    assert decision.model_key == "general"
