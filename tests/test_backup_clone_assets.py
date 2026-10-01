"""
tests/test_backup_clone_assets.py
=====================================
Test di clone_emoji/clone_stickers/clone_soundboard/clone_webhooks —
con oggetti finti minimi (queste funzioni non fanno isinstance su
tipi discord.py, solo chiamate a metodi/attributi, quindi non serve
ereditare da classi reali come per i ruoli/canali).
"""

import pytest

from core.backup_clone_logic import (
    clone_emoji,
    clone_soundboard,
    clone_stickers,
    clone_webhooks,
)


class _FakeEmoji:
    def __init__(self, name: str, contenuto: bytes, animated: bool = False) -> None:
        self.name = name
        self.animated = animated
        self._contenuto = contenuto

    async def read(self) -> bytes:
        return self._contenuto


class _FakeSticker:
    def __init__(self, name: str, description: str, emoji: str, contenuto: bytes) -> None:
        self.name = name
        self.description = description
        self.emoji = emoji
        self._contenuto = contenuto

    async def read(self) -> bytes:
        return self._contenuto


class _FakeSoundboardSound:
    def __init__(self, name: str, volume: float, emoji, contenuto: bytes) -> None:
        self.name = name
        self.volume = volume
        self.emoji = emoji
        self._contenuto = contenuto

    async def read(self) -> bytes:
        return self._contenuto


class _FakeWebhook:
    def __init__(self, name: str, channel_id: int) -> None:
        self.name = name
        self.channel_id = channel_id


class _FakeTargetChannel:
    def __init__(self, channel_id: int) -> None:
        self.id = channel_id
        self.chiamate_create_webhook: list[dict] = []

    async def create_webhook(self, **kwargs) -> None:
        self.chiamate_create_webhook.append(kwargs)


class _FakeSourceGuildAssets:
    def __init__(self, emojis=None, stickers=None, soundboard_sounds=None, webhooks_list=None) -> None:
        self.emojis = emojis or []
        self.stickers = stickers or []
        self.soundboard_sounds = soundboard_sounds or []
        self._webhooks_list = webhooks_list or []

    async def webhooks(self):
        return self._webhooks_list


class _FakeTargetGuildAssets:
    def __init__(
        self,
        canali: dict[int, _FakeTargetChannel] | None = None,
        emoji_limit: int = 50,
        sticker_limit: int = 5,
    ) -> None:
        self.emoji_limit = emoji_limit
        self.sticker_limit = sticker_limit
        self.chiamate_create_custom_emoji: list[dict] = []
        self.chiamate_create_sticker: list[dict] = []
        self.chiamate_create_soundboard_sound: list[dict] = []
        self._canali = canali or {}

    async def create_custom_emoji(self, **kwargs) -> None:
        self.chiamate_create_custom_emoji.append(kwargs)

    async def create_sticker(self, **kwargs) -> None:
        self.chiamate_create_sticker.append(kwargs)

    async def create_soundboard_sound(self, **kwargs) -> None:
        self.chiamate_create_soundboard_sound.append(kwargs)

    def get_channel(self, channel_id: int):
        return self._canali.get(channel_id)


@pytest.mark.asyncio
async def test_clone_emoji_scarica_e_ricrea():
    emoji = _FakeEmoji("pepehands", b"immagine finta")
    source = _FakeSourceGuildAssets(emojis=[emoji])
    target = _FakeTargetGuildAssets()

    await clone_emoji(source, target)

    assert len(target.chiamate_create_custom_emoji) == 1
    chiamata = target.chiamate_create_custom_emoji[0]
    assert chiamata["name"] == "pepehands"
    assert chiamata["image"] == b"immagine finta"


@pytest.mark.asyncio
async def test_clone_emoji_multiple_in_ordine():
    source = _FakeSourceGuildAssets(
        emojis=[_FakeEmoji("uno", b"a"), _FakeEmoji("due", b"b")]
    )
    target = _FakeTargetGuildAssets()

    await clone_emoji(source, target)

    nomi = [c["name"] for c in target.chiamate_create_custom_emoji]
    assert nomi == ["uno", "due"]


@pytest.mark.asyncio
async def test_clone_stickers_scarica_e_ricrea():
    sticker = _FakeSticker("saluto", "Un saluto", "👋", b"immagine sticker")
    source = _FakeSourceGuildAssets(stickers=[sticker])
    target = _FakeTargetGuildAssets()

    await clone_stickers(source, target)

    chiamata = target.chiamate_create_sticker[0]
    assert chiamata["name"] == "saluto"
    assert chiamata["description"] == "Un saluto"
    assert chiamata["emoji"] == "👋"
    # Il file deve avvolgere i byte scaricati (BytesIO, non i byte
    # grezzi direttamente - discord.File tratterebbe bytes grezzi
    # come un PERCORSO FILE, non contenuto, trovato con un test
    # diretto prima di scrivere questo codice).
    assert chiamata["file"].fp.read() == b"immagine sticker"


@pytest.mark.asyncio
async def test_clone_soundboard_scarica_e_ricrea():
    suono = _FakeSoundboardSound("applausi", 0.8, "👏", b"audio finto")
    source = _FakeSourceGuildAssets(soundboard_sounds=[suono])
    target = _FakeTargetGuildAssets()

    await clone_soundboard(source, target)

    chiamata = target.chiamate_create_soundboard_sound[0]
    assert chiamata["name"] == "applausi"
    assert chiamata["sound"] == b"audio finto"
    assert chiamata["volume"] == 0.8
    assert chiamata["emoji"] == "👏"


@pytest.mark.asyncio
async def test_clone_webhooks_instrada_verso_il_canale_clonato():
    webhook = _FakeWebhook("Notifiche", channel_id=100)
    source = _FakeSourceGuildAssets(webhooks_list=[webhook])

    canale_clonato = _FakeTargetChannel(200)
    target = _FakeTargetGuildAssets(canali={200: canale_clonato})

    await clone_webhooks(source, target, channel_id_map={100: 200})

    assert len(canale_clonato.chiamate_create_webhook) == 1
    assert canale_clonato.chiamate_create_webhook[0]["name"] == "Notifiche"


@pytest.mark.asyncio
async def test_clone_webhooks_canale_non_clonato_viene_saltato_senza_sollevare():
    webhook = _FakeWebhook("Notifiche", channel_id=999)  # non nella mappa
    source = _FakeSourceGuildAssets(webhooks_list=[webhook])
    target = _FakeTargetGuildAssets()

    await clone_webhooks(source, target, channel_id_map={})  # non deve sollevare


# ---- §12 11.5–11.7: i limiti del server di destinazione ---------------


@pytest.mark.asyncio
async def test_clone_emoji_salta_quelle_oltre_il_limite_e_le_conta():
    source = _FakeSourceGuildAssets(
        emojis=[_FakeEmoji("uno", b"a"), _FakeEmoji("due", b"b"), _FakeEmoji("tre", b"c")]
    )
    target = _FakeTargetGuildAssets(emoji_limit=2)

    saltate = await clone_emoji(source, target)

    assert [c["name"] for c in target.chiamate_create_custom_emoji] == ["uno", "due"]
    assert saltate == 1


@pytest.mark.asyncio
async def test_clone_emoji_il_limite_e_separato_per_statiche_e_animate():
    source = _FakeSourceGuildAssets(
        emojis=[
            _FakeEmoji("fissa", b"a"),
            _FakeEmoji("mossa", b"b", animated=True),
            _FakeEmoji("fissa2", b"c"),
        ]
    )
    target = _FakeTargetGuildAssets(emoji_limit=1)

    saltate = await clone_emoji(source, target)

    assert [c["name"] for c in target.chiamate_create_custom_emoji] == ["fissa", "mossa"]
    assert saltate == 1


@pytest.mark.asyncio
async def test_clone_emoji_un_errore_di_discord_salta_solo_quella():
    import discord
    from unittest.mock import MagicMock

    source = _FakeSourceGuildAssets(emojis=[_FakeEmoji("rotta", b"a"), _FakeEmoji("ok", b"b")])
    target = _FakeTargetGuildAssets()
    originale = target.create_custom_emoji

    async def create_che_rifiuta_la_prima(**kwargs):
        if kwargs["name"] == "rotta":
            raise discord.HTTPException(MagicMock(status=400, reason="x"), "file troppo grande")
        await originale(**kwargs)

    target.create_custom_emoji = create_che_rifiuta_la_prima

    saltate = await clone_emoji(source, target)

    assert [c["name"] for c in target.chiamate_create_custom_emoji] == ["ok"]
    assert saltate == 1


@pytest.mark.asyncio
async def test_clone_stickers_salta_quelli_oltre_il_limite():
    source = _FakeSourceGuildAssets(
        stickers=[_FakeSticker(f"s{i}", "d", "👋", b"x") for i in range(3)]
    )
    target = _FakeTargetGuildAssets(sticker_limit=2)

    saltati = await clone_stickers(source, target)

    assert len(target.chiamate_create_sticker) == 2
    assert saltati == 1


@pytest.mark.asyncio
async def test_clone_soundboard_salta_i_suoni_oltre_il_limite():
    from core.backup_clone_logic import MAX_SUONI_SOUNDBOARD

    suoni = [_FakeSoundboardSound(f"s{i}", 1.0, None, b"x") for i in range(MAX_SUONI_SOUNDBOARD + 2)]
    source = _FakeSourceGuildAssets(soundboard_sounds=suoni)
    target = _FakeTargetGuildAssets()

    saltati = await clone_soundboard(source, target)

    assert len(target.chiamate_create_soundboard_sound) == MAX_SUONI_SOUNDBOARD
    assert saltati == 2
