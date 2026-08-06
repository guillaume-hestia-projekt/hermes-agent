"""Regression test for TUI approval-prompt credential redaction (#48456).

Follow-up to #50767, which redacted the chat-platform and SSE/API approval
transports. The TUI JSON-RPC transport is the third egress: three
`register_gateway_notify` callbacks in `tui_gateway/server.py` emit the raw
`approval_data` (with an unredacted `command`) to the TUI client. They now
route through the module-level `_emit_approval_request` helper, which redacts
`payload["command"]` via the shared `gateway.run._redact_approval_command` seam
before emitting.
"""

import inspect

import pytest


class TestTuiApprovalEmitRedaction:
    def test_emit_approval_request_redacts_command_in_payload(self, monkeypatch):
        from tui_gateway import server as tui_server

        emitted = {}
        monkeypatch.setattr(
            tui_server, "_emit",
            lambda event, sid, payload=None: emitted.update(
                {"event": event, "sid": sid, "payload": payload}
            ),
        )
        raw = "curl -H 'Authorization: token ghp_01...6789' https://api.github.com"
        tui_server._emit_approval_request("sess-1", {"command": raw, "description": "x"})

        assert emitted["event"] == "approval.request"
        # credential removed, non-command field + command structure preserved
        assert "ghp_01...6789" not in emitted["payload"]["command"]
        assert emitted["payload"]["description"] == "x"
        assert "github.com" in emitted["payload"]["command"]

    def test_url_mode_keeps_full_target_for_pre_consent_review(self, monkeypatch):
        from tui_gateway import server as tui_server

        emitted = {}
        monkeypatch.setattr(
            tui_server, "_emit",
            lambda event, sid, payload=None: emitted.update(
                {"event": event, "sid": sid, "payload": payload}
            ),
        )
        url = "https://auth.example.test/connect?state=opaque"
        tui_server._emit_approval_request(
            "sess-1",
            {
                "choices": ["once", "deny"],
                "command": url,
                "description": "Target host: auth.example.test",
                "elicitation_mode": "url",
                "server_name": "workspace",
            },
        )

        assert emitted["event"] == "approval.request"
        assert emitted["payload"]["command"] == url
        assert emitted["payload"]["choices"] == ["once", "deny"]

    def test_post_consent_url_uses_distinct_navigation_event(self, monkeypatch):
        from tui_gateway import server as tui_server

        emitted = {}
        monkeypatch.setattr(
            tui_server, "_emit",
            lambda event, sid, payload=None: emitted.update(
                {"event": event, "sid": sid, "payload": payload}
            ),
        )
        tui_server._emit_approval_request(
            "sess-1",
            {
                "kind": "mcp.elicitation.url",
                "message": "Authorize",
                "server_name": "workspace",
                "url": "https://auth.example.test/connect?state=opaque",
            },
        )

        assert emitted == {
            "event": "mcp.elicitation.url",
            "sid": "sess-1",
            "payload": {
                "message": "Authorize",
                "server_name": "workspace",
                "url": "https://auth.example.test/connect?state=opaque",
            },
        }

