"""Tests for the MCP elicitation handler in tools.mcp_tool.

These tests exercise ElicitationHandler in isolation -- the underlying
approval system and the MCP transport layer are mocked, so no real MCP
server or user input is required.

Tests skip cleanly if the optional `mcp` SDK is not installed (it is an
optional dependency under the `[mcp]` extra).
"""

import asyncio
from unittest.mock import patch

import pytest


pytest.importorskip("mcp.types")

from mcp.types import ElicitResult  # noqa: E402  -- after importorskip

from tools.mcp_tool import (  # noqa: E402
    ElicitationURLValidationError,
    ElicitationHandler,
    _elicitation_url_origin,
    _format_elicitation_schema_summary,
    _format_url_elicitation_description,
    _validate_elicitation_url,
)


def _form_params(message="please confirm", schema=None):
    """Build a stand-in for ElicitRequestFormParams.

    We use a plain object (not the SDK type directly) so the test doesn't
    couple to optional Pydantic validation -- the handler reads fields via
    getattr() and tolerates duck-typed inputs.
    """
    from types import SimpleNamespace
    return SimpleNamespace(
        mode="form",
        message=message,
        requested_schema=schema or {},
    )


def _url_params(message="open this url", url="https://example.com/auth", elicitation_id="e1"):
    from types import SimpleNamespace
    return SimpleNamespace(
        mode="url",
        message=message,
        url=url,
        elicitation_id=elicitation_id,
    )


class TestSchemaSummary:
    def test_empty_schema_falls_back_to_generic_message(self):
        out = _format_elicitation_schema_summary({}, "pay")
        assert "pay" in out
        assert "Approval requested" in out

    def test_properties_render_with_type_and_description(self):
        schema = {
            "type": "object",
            "properties": {
                "amount": {"type": "string", "description": "USD amount"},
                "recipient": {"type": "string"},
            },
        }
        out = _format_elicitation_schema_summary(schema, "pay")
        assert "amount (string): USD amount" in out
        assert "recipient (string)" in out


class TestURLValidation:
    @pytest.mark.parametrize(
        "url",
        [
            "https://example.com/connect?state=abc123",
            "http://localhost:8765/callback",
            "http://127.0.0.1:8765/callback",
            "http://[::1]:8765/callback",
        ],
    )
    def test_accepts_https_and_loopback_http(self, url):
        assert _validate_elicitation_url(url) == url

    @pytest.mark.parametrize(
        "url",
        [
            "http://example.com/connect",
            "javascript:alert(1)",
            "file:///etc/passwd",
            "https://user:pass@example.com/connect",
            "https://example.com/connect\nX-Injected: yes",
            "https://example.com/`break-markdown`",
            "https://example.com/connect\u200bspoofed",
            "https://example.com/connect\u202eevil",
            " https://example.com/connect",
            "https://example.com/" + "x" * 2049,
        ],
    )
    def test_rejects_unsafe_targets(self, url):
        with pytest.raises(ElicitationURLValidationError):
            _validate_elicitation_url(url)

    def test_origin_omits_query_and_default_port(self):
        assert (
            _elicitation_url_origin("https://example.com:443/connect?state=secret")
            == "https://example.com"
        )

    def test_description_identifies_server_host_and_punycode(self):
        out = _format_url_elicitation_description(
            "Authorize the workspace action",
            "https://xn--exmple-cua.test/connect",
            "workspace",
        )
        assert "workspace" in out
        assert "xn--exmple-cua.test" in out
        assert "Punycode" in out

    def test_description_neutralizes_server_markup_and_mentions(self):
        out = _format_url_elicitation_description(
            "Approve <@everyone> [click](https://evil.test)",
            "https://auth.example.test/connect",
            "workspace`<!channel>",
        )

        assert "@everyone" not in out
        assert "<!channel>" not in out
        assert "[click](" not in out


class TestElicitationHandlerFormMode:
    def test_user_accepts_once_returns_accept(self):
        handler = ElicitationHandler("pay", {"timeout": 5})
        params = _form_params(
            "authorize a payment of $0.50",
            {"properties": {"approved": {"type": "boolean"}}},
        )

        with patch("tools.approval.request_elicitation_consent", return_value="accept"):
            result = asyncio.run(handler(context=None, params=params))

        assert isinstance(result, ElicitResult)
        assert result.action == "accept"
        assert result.content == {}
        assert handler.metrics["accepted"] == 1
        assert handler.metrics["declined"] == 0


    def test_cancel_propagates_through(self):
        """request_elicitation_consent returns 'cancel' when the gateway
        wait times out (resolved=False). The handler should propagate
        that as ElicitResult(action='cancel') so the server can
        distinguish 'no answer' from 'no'."""
        handler = ElicitationHandler("pay", {"timeout": 5})
        params = _form_params()

        with patch("tools.approval.request_elicitation_consent", return_value="cancel"):
            result = asyncio.run(handler(context=None, params=params))

        assert result.action == "cancel"
        assert handler.metrics["errors"] == 1


class TestElicitationHandlerFailureModes:
    def test_url_mode_opens_only_through_one_shot_consent(self):
        handler = ElicitationHandler("pay", {"timeout": 5})
        url = "https://example.com/auth?state=opaque"
        params = _url_params(url=url)

        with patch("tools.approval.request_elicitation_consent", return_value="accept") as consent:
            result = asyncio.run(handler(context=None, params=params))

        assert result.action == "accept"
        assert result.content is None
        assert handler.metrics["accepted"] == 1
        assert consent.call_args.kwargs["url"] == url
        assert consent.call_args.kwargs["server_name"] == "pay"

    def test_url_mode_decline_propagates_without_content(self):
        handler = ElicitationHandler("pay", {"timeout": 5})

        with patch("tools.approval.request_elicitation_consent", return_value="decline"):
            result = asyncio.run(handler(context=None, params=_url_params()))

        assert result.action == "decline"
        assert result.content is None
        assert handler.metrics["declined"] == 1

    def test_invalid_url_is_declined_without_prompting_or_logging_query(self, caplog):
        handler = ElicitationHandler("pay", {"timeout": 5})
        raw = "https://user:pass@example.com/connect?state=do-not-log"

        with patch(
            "tools.approval.request_elicitation_consent",
            side_effect=AssertionError("invalid URL must not prompt"),
        ):
            result = asyncio.run(handler(context=None, params=_url_params(url=raw)))

        assert result.action == "decline"
        assert "do-not-log" not in caplog.text

    def test_exception_in_approval_fails_closed_to_decline(self):
        handler = ElicitationHandler("pay", {"timeout": 5})
        params = _form_params()

        with patch(
            "tools.approval.request_elicitation_consent",
            side_effect=RuntimeError("approval system blew up"),
        ):
            result = asyncio.run(handler(context=None, params=params))

        assert result.action == "decline"
        assert handler.metrics["errors"] == 1

    def test_timeout_returns_cancel(self, monkeypatch):
        # Shrink the outer grace window so the test budget is just the
        # handler timeout. Default grace is 5s, which makes stall durations
        # tight and the test flaky.
        monkeypatch.setattr(
            ElicitationHandler, "_OUTER_TIMEOUT_GRACE_SECONDS", 0
        )
        # _safe_numeric clamps `timeout` to a minimum of 1s, so the
        # effective wait_for budget is 1s here. Stall longer than that
        # so the wait_for reliably fires TimeoutError.
        handler = ElicitationHandler("pay", {"timeout": 0.05})
        params = _form_params()

        def stall(*_args, **_kwargs):
            import time as _t
            _t.sleep(2)
            return "accept"

        with patch("tools.approval.request_elicitation_consent", side_effect=stall):
            result = asyncio.run(handler(context=None, params=params))

        assert result.action == "cancel"
        assert handler.metrics["errors"] == 1


class TestElicitationHandlerWiring:
    def test_session_kwargs_returns_callback(self):
        handler = ElicitationHandler("pay", {})
        kwargs = handler.session_kwargs()
        assert kwargs == {"elicitation_callback": handler}


    def test_disabled_config_does_not_construct_handler(self):
        """The server task initializer checks ``elicitation.enabled`` --
        an explicit ``False`` should suppress handler creation. The unit
        of that decision lives in MCPServerTask, but the handler itself
        must remain harmless to instantiate with arbitrary config."""
        handler = ElicitationHandler("pay", {"enabled": False, "timeout": 10})
        # Just confirm it instantiates and reads timeout; the gate lives
        # at the higher layer.
        assert handler.timeout == 10


class TestElicitationHandlerContextBridge:
    """The MCP recv-loop task that fires elicitation callbacks does NOT
    inherit the agent's contextvars (HERMES_SESSION_PLATFORM etc.). The
    handler reads ``owner._pending_call_context`` -- a snapshot captured
    by the MCP tool wrapper around ``session.call_tool`` -- and replays
    it before invoking the approval router so gateway-session detection
    survives the task hop. Regression tests for that bridge."""

    def test_captured_context_is_replayed_in_consent_call(self):
        """The captured context's contextvar values must be observable
        when ``request_elicitation_consent`` runs -- otherwise the
        gateway-platform detection in approval.py sees an empty platform
        string and falls back to the CLI path (the bug this fixes)."""
        import contextvars
        from types import SimpleNamespace

        probe: contextvars.ContextVar[str] = contextvars.ContextVar(
            "elicitation_test_probe", default=""
        )
        seen: list[str] = []

        def fake_consent(*_args, **_kwargs):
            seen.append(probe.get())
            return "accept"

        token = probe.set("gateway:telegram")
        try:
            captured = contextvars.copy_context()
        finally:
            probe.reset(token)
        assert probe.get() == "", (
            "Sanity check: the probe must be empty outside the captured "
            "context, otherwise the test would pass even without replay."
        )

        owner = SimpleNamespace(_pending_call_context=captured)
        handler = ElicitationHandler("pay", {"timeout": 5}, owner=owner)
        params = _form_params()

        with patch("tools.approval.request_elicitation_consent", side_effect=fake_consent):
            result = asyncio.run(handler(context=None, params=params))

        assert result.action == "accept"
        assert seen == ["gateway:telegram"], (
            f"Expected the captured contextvar to be visible inside the "
            f"consent call; got {seen!r}"
        )

    def test_missing_captured_context_falls_back_to_direct_call(self):
        """Without an owner (or with an owner that hasn't entered a tool
        call) the handler must still invoke the consent router -- just
        without the contextvar replay. Otherwise CLI/TUI sessions, which
        don't set HERMES_SESSION_PLATFORM, would break."""
        handler = ElicitationHandler("pay", {"timeout": 5}, owner=None)
        params = _form_params()

        with patch("tools.approval.request_elicitation_consent", return_value="accept") as m:
            result = asyncio.run(handler(context=None, params=params))

        assert result.action == "accept"
        assert m.call_count == 1


    def test_pending_call_context_none_does_not_crash(self):
        """``owner._pending_call_context`` is set to None between tool
        calls. An elicitation arriving in that window must not crash."""
        from types import SimpleNamespace

        owner = SimpleNamespace(_pending_call_context=None)
        handler = ElicitationHandler("pay", {"timeout": 5}, owner=owner)
        params = _form_params()

        with patch("tools.approval.request_elicitation_consent", return_value="decline"):
            result = asyncio.run(handler(context=None, params=params))

        assert result.action == "decline"
