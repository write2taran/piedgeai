from piedgeai.sessions import SessionStore


def test_session_store_roundtrip(tmp_path):
    store = SessionStore(tmp_path / "sessions.sqlite3")
    session_id = store.ensure_session()
    store.append(session_id, "user", "hello")
    store.append(session_id, "assistant", "hi")

    history = store.history(session_id)
    assert [message.role for message in history] == ["user", "assistant"]
    assert "user: hello" in store.as_prompt_context(session_id)
