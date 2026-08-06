"""Behavior contract for MCP URL-mode elicitation approval and presentation."""

from unittest.mock import patch

import pytest

from tools import approval


@pytest.fixture(autouse=True)
def _clean_gateway_state(monkeypatch):
    monkeypatch.delenv("HERMES_GATEWAY_SESSION", raising=False)
    yield
    approval.unregister_gateway_notify("mcp-url-test")


def _run_gateway_decision(choice: str, *, presenter_raises: bool = False):
    monkeypatch_data = []
    token = approval.set_current_session_key("mcp-url-test")

    def notify(data):
        monkeypatch_data.append(data)
        if data.get("kind") == "mcp.elicitation.url":
            if presenter_raises:
                raise RuntimeError("surface unavailable")
            return
        approval.resolve_gateway_approval("mcp-url-test", choice)

    approval.register_gateway_notify("mcp-url-test", notify)
    try:
        with patch.dict("os.environ", {"HERMES_GATEWAY_SESSION": "1"}):
            result = approval.request_elicitation_consent(
                "Authorize this action",
                "MCP server 'workspace' wants to open an external page.\n"
                "Target host: auth.example.test",
                surface="mcp-elicitation/workspace",
                url="https://auth.example.test/connect?state=opaque",
                server_name="workspace",
            )
    finally:
        approval.unregister_gateway_notify("mcp-url-test")
        approval.reset_current_session_key(token)
    return result, monkeypatch_data


def test_gateway_opens_only_after_one_shot_consent():
    result, events = _run_gateway_decision("once")

    assert result == "accept"
    assert events[0]["choices"] == ["once", "deny"]
    assert events[0]["allow_session"] is False
    assert events[0]["command"].endswith("state=opaque")
    assert events[1] == {
        "kind": "mcp.elicitation.url",
        "message": "Authorize this action",
        "server_name": "workspace",
        "url": "https://auth.example.test/connect?state=opaque",
    }


@pytest.mark.parametrize("choice", ["deny", "session", "always"])
def test_gateway_non_once_choices_never_present_url(choice):
    result, events = _run_gateway_decision(choice)

    assert result == "decline"
    assert len(events) == 1


def test_gateway_presentation_failure_cancels_after_consent():
    result, events = _run_gateway_decision("once", presenter_raises=True)

    assert result == "cancel"
    assert len(events) == 2


def test_url_query_is_not_forwarded_to_approval_hooks(monkeypatch):
    hooks = []
    monkeypatch.setattr(approval, "_fire_approval_hook", lambda name, **kwargs: hooks.append((name, kwargs)))

    result, _events = _run_gateway_decision("deny")

    assert result == "decline"
    assert hooks
    assert all("state=opaque" not in item[1]["command"] for item in hooks)
    assert all("workspace" in item[1]["command"] for item in hooks)


def test_local_cli_uses_once_only_prompt_then_external_browser():
    callback = object()
    with (
        patch("tools.approval.prompt_dangerous_approval", return_value="once") as prompt,
        patch("tools.approval._open_external_elicitation_url", return_value=True) as browser,
    ):
        result = approval.request_elicitation_consent(
            "Authorize this action",
            "Target host: auth.example.test",
            url="https://auth.example.test/connect?state=opaque",
            server_name="workspace",
            approval_callback=callback,
        )

    assert result == "accept"
    assert prompt.call_args.kwargs["once_only"] is True
    assert prompt.call_args.kwargs["redact_command"] is False
    assert prompt.call_args.kwargs["approval_callback"] is callback
    browser.assert_called_once_with("https://auth.example.test/connect?state=opaque")


def test_local_browser_failure_returns_cancel():
    with (
        patch("tools.approval.prompt_dangerous_approval", return_value="once"),
        patch("tools.approval._open_external_elicitation_url", return_value=False),
    ):
        result = approval.request_elicitation_consent(
            "Authorize this action",
            "Target host: auth.example.test",
            url="https://auth.example.test/connect",
            server_name="workspace",
        )

    assert result == "cancel"


def test_local_opener_uses_one_shell_free_argv(monkeypatch):
    popen_calls = []
    monkeypatch.setattr(approval.sys, "platform", "linux")
    monkeypatch.setattr(approval.shutil, "which", lambda executable: f"/usr/bin/{executable}")
    monkeypatch.setattr(
        approval.subprocess,
        "Popen",
        lambda argv, **kwargs: popen_calls.append((argv, kwargs)),
    )

    url = "https://auth.example.test/connect?a=1&b=2%7Cwhoami"
    assert approval._open_external_elicitation_url(url) is True
    assert popen_calls[0][0] == ["/usr/bin/xdg-open", url]
    assert "shell" not in popen_calls[0][1]


@pytest.mark.parametrize(
    "url",
    [
        "http://example.test/connect",
        "https://user:password@example.test/connect",
        "file:///etc/passwd",
    ],
)
def test_direct_consent_call_revalidates_url_before_prompt(url):
    with patch("tools.approval.prompt_dangerous_approval") as prompt:
        result = approval.request_elicitation_consent(
            "Authorize this action",
            "Target host: example.test",
            url=url,
            server_name="workspace",
        )

    assert result == "decline"
    prompt.assert_not_called()
