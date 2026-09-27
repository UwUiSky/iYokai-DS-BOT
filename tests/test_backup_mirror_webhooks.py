"""
tests/test_backup_mirror_webhooks.py
========================================
Test di create_mirror_webhooks() (SPEC.md §11.9) — crea un webhook
dedicato al mirroring in OGNI canale testuale clonato, restituendo
la mappa canale_originale -> URL_webhook.
"""

import discord
import pytest

from core.backup_clone_logic import create_mirror_webhooks


class _FakeWebhookCreato:
    def __init__(self, url: str) -> None:
        self.url = url


class _FakeTargetTextChannel(discord.TextChannel):
    def __init__(self, ch_id: int, webhook_url: str) -> None:
        self.id = ch_id
        self._webhook_url = webhook_url
        self.chiamate_create_webhook: list[dict] = []

    async def create_webhook(self, **kwargs):
        self.chiamate_create_webhook.append(kwargs)
        return _FakeWebhookCreato(self._webhook_url)


class _FakeTargetVoiceChannel(discord.VoiceChannel):
    def __init__(self, ch_id: int) -> None:
        self.id = ch_id


class _FakeTargetGuild:
    def __init__(self, channels_by_id: dict) -> None:
        self._channels_by_id = channels_by_id

    def get_channel(self, channel_id: int):
        return self._channels_by_id.get(channel_id)


@pytest.mark.asyncio
async def test_crea_un_webhook_per_canale_testuale_clonato():
    canale_clonato = _FakeTargetTextChannel(200, "https://discord.com/api/webhooks/abc")
    target = _FakeTargetGuild({200: canale_clonato})

    mappa = await create_mirror_webhooks(target, channel_id_map={100: 200})

    assert mappa == {100: "https://discord.com/api/webhooks/abc"}
    assert canale_clonato.chiamate_create_webhook[0]["name"] == "iYokai Mirror"


@pytest.mark.asyncio
async def test_ignora_i_canali_vocali():
    canale_vocale = _FakeTargetVoiceChannel(300)
    target = _FakeTargetGuild({300: canale_vocale})

    mappa = await create_mirror_webhooks(target, channel_id_map={150: 300})

    assert mappa == {}


@pytest.mark.asyncio
async def test_canale_non_trovato_viene_saltato_senza_sollevare():
    target = _FakeTargetGuild({})

    mappa = await create_mirror_webhooks(target, channel_id_map={100: 999})

    assert mappa == {}


@pytest.mark.asyncio
async def test_piu_canali_testuali_producono_piu_voci_nella_mappa():
    canale_a = _FakeTargetTextChannel(201, "https://discord.com/api/webhooks/a")
    canale_b = _FakeTargetTextChannel(202, "https://discord.com/api/webhooks/b")
    target = _FakeTargetGuild({201: canale_a, 202: canale_b})

    mappa = await create_mirror_webhooks(target, channel_id_map={101: 201, 102: 202})

    assert mappa == {
        101: "https://discord.com/api/webhooks/a",
        102: "https://discord.com/api/webhooks/b",
    }
