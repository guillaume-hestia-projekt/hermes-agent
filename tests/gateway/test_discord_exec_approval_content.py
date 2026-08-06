from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gateway.config import PlatformConfig
import plugins.platforms.discord.adapter as discord_adapter
from plugins.platforms.discord.adapter import DiscordAdapter


def _capture_channel(adapter):
    sent = {}

    async def fake_send(**kwargs):
        sent.update(kwargs)
        return SimpleNamespace(id=1234)

    channel = SimpleNamespace(send=AsyncMock(side_effect=fake_send))
    adapter._client = SimpleNamespace(
        get_channel=lambda _chat_id: channel,
        fetch_channel=AsyncMock(),
    )
    return sent


@pytest.mark.asyncio
async def test_exec_approval_prompt_uses_visible_content_with_command_and_reason():
    adapter = DiscordAdapter(PlatformConfig(enabled=True, token="***"))
    sent = _capture_channel(adapter)

    command = "python scripts/deploy.py --env prod --force"
    result = await adapter.send_exec_approval(
        chat_id="555",
        command=command,
        session_key="discord:555",
        description="script execution via -c flag",
    )

    assert result.success is True
    assert sent["view"] is not None
    assert sent["embed"] is not None

    prompt_text = sent["content"]
    assert "Command Approval Required" in prompt_text
    assert "Do you want Hermes to run this command?" in prompt_text
    assert "Requested command" in prompt_text
    assert command in prompt_text
    assert "Reason" in prompt_text
    assert "script execution via -c flag" in prompt_text


@pytest.mark.asyncio
async def test_mcp_url_approval_is_complete_and_suppresses_embeds(monkeypatch):
    adapter = DiscordAdapter(PlatformConfig(enabled=True, token="***"))
    sent = _capture_channel(adapter)
    url = "https://auth.example.test/connect?state=opaque"
    monkeypatch.setattr(
        discord_adapter,
        "ExecApprovalView",
        lambda **_kwargs: SimpleNamespace(_message=None),
    )

    result = await adapter.send_exec_approval(
        chat_id="555",
        command=url,
        session_key="mcp-url",
        description="MCP server workspace requested this external page",
        metadata={"require_full_command": True, "suppress_link_preview": True},
        allow_permanent=False,
        allow_session=False,
    )

    assert result.success is True
    assert adapter.supports_mcp_url_elicitation is True
    assert url in sent["content"]
    assert sent["suppress_embeds"] is True
    assert "embed" not in sent


@pytest.mark.asyncio
async def test_mcp_url_approval_fails_instead_of_truncating():
    adapter = DiscordAdapter(PlatformConfig(enabled=True, token="***"))
    sent = _capture_channel(adapter)

    result = await adapter.send_exec_approval(
        chat_id="555",
        command="https://auth.example.test/" + "a" * 2000,
        session_key="mcp-url",
        metadata={"require_full_command": True, "suppress_link_preview": True},
        allow_permanent=False,
        allow_session=False,
    )

    assert result.success is False
    assert "full" in (result.error or "")
    assert sent == {}


@pytest.mark.asyncio
async def test_post_consent_link_is_verbatim_and_suppresses_embeds():
    adapter = DiscordAdapter(PlatformConfig(enabled=True, token="***"))
    sent = _capture_channel(adapter)
    url = "https://auth.example.test/connect?state=abc_def&return=%2Fdone"

    result = await adapter.send_mcp_elicitation_url(
        chat_id="555",
        metadata={},
        server_name="workspace",
        url=url,
    )

    assert result.success is True
    assert sent["content"].endswith(url)
    assert sent["suppress_embeds"] is True


@pytest.mark.asyncio
async def test_post_consent_link_fails_closed_in_forum_parent():
    adapter = DiscordAdapter(PlatformConfig(enabled=True, token="***"))
    forum = SimpleNamespace(type=SimpleNamespace(value=15), send=AsyncMock())
    adapter._client = SimpleNamespace(
        get_channel=lambda _chat_id: forum,
        fetch_channel=AsyncMock(),
    )

    result = await adapter.send_mcp_elicitation_url(
        chat_id="555",
        metadata={},
        server_name="workspace",
        url="https://auth.example.test/connect?state=opaque",
    )

    assert result.success is False
    assert result.retryable is False
    forum.send.assert_not_awaited()
