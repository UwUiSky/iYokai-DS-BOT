"""
tests/test_backup_clone_channels.py
=======================================
Test di clone_categories_and_channels() con oggetti finti che
replicano l'interfaccia REALE di discord.py (category/overwrites
sono property complesse definite in discord.abc.GuildChannel,
sovrascritte qui con versioni semplici — stesso approccio già
verificato per Role.permissions/colour).
"""

import discord
import pytest

from core.backup_clone_logic import clone_categories_and_channels


class _FakeCategory(discord.CategoryChannel):
    def __init__(self, cat_id: int, name: str, position: int, overwrites=None) -> None:
        self.id = cat_id
        self.name = name
        self.position = position
        self._overwrites_finti = overwrites or {}

    @property
    def overwrites(self):
        return self._overwrites_finti


class _FakeTextChannel(discord.TextChannel):
    def __init__(
        self, ch_id: int, name: str, position: int, category=None,
        topic: str = "", nsfw: bool = False, slowmode_delay: int = 0, overwrites=None,
    ) -> None:
        self.id = ch_id
        self.name = name
        self.position = position
        self._category_finta = category
        self.topic = topic
        self.nsfw = nsfw
        self.slowmode_delay = slowmode_delay
        self._overwrites_finti = overwrites or {}

    @property
    def category(self):
        return self._category_finta

    @property
    def overwrites(self):
        return self._overwrites_finti


class _FakeVoiceChannel(discord.VoiceChannel):
    def __init__(
        self, ch_id: int, name: str, position: int, category=None,
        bitrate: int = 64000, user_limit: int = 0, overwrites=None,
    ) -> None:
        self.id = ch_id
        self.name = name
        self.position = position
        self._category_finta = category
        self.bitrate = bitrate
        self.user_limit = user_limit
        self._overwrites_finti = overwrites or {}

    @property
    def category(self):
        return self._category_finta

    @property
    def overwrites(self):
        return self._overwrites_finti


class _FakeSourceGuild:
    def __init__(self, categories: list, channels: list) -> None:
        self.categories = categories
        self.channels = channels


class _FakeCreatedCategory:
    def __init__(self, cat_id: int, name: str) -> None:
        self.id = cat_id
        self.name = name


class _FakeCreatedChannel:
    def __init__(self, ch_id: int, name: str) -> None:
        self.id = ch_id
        self.name = name


class _FakeTargetGuild:
    def __init__(self) -> None:
        self.chiamate_create_category: list[dict] = []
        self.chiamate_create_text_channel: list[dict] = []
        self.chiamate_create_voice_channel: list[dict] = []
        self._prossimo_id = 9000

    async def create_category(self, **kwargs):
        self.chiamate_create_category.append(kwargs)
        nuovo = _FakeCreatedCategory(self._prossimo_id, kwargs["name"])
        self._prossimo_id += 1
        return nuovo

    async def create_text_channel(self, **kwargs):
        self.chiamate_create_text_channel.append(kwargs)
        nuovo = _FakeCreatedChannel(self._prossimo_id, kwargs["name"])
        self._prossimo_id += 1
        return nuovo

    async def create_voice_channel(self, **kwargs):
        self.chiamate_create_voice_channel.append(kwargs)
        nuovo = _FakeCreatedChannel(self._prossimo_id, kwargs["name"])
        self._prossimo_id += 1
        return nuovo


@pytest.mark.asyncio
async def test_clona_categorie_prima_dei_canali():
    categoria = _FakeCategory(1, "Generale", position=0)
    canale_testuale = _FakeTextChannel(2, "chat", position=0, category=categoria)

    source = _FakeSourceGuild(categories=[categoria], channels=[categoria, canale_testuale])
    target = _FakeTargetGuild()

    await clone_categories_and_channels(source, target, role_id_map={})

    assert len(target.chiamate_create_category) == 1
    assert target.chiamate_create_category[0]["name"] == "Generale"
    assert len(target.chiamate_create_text_channel) == 1
    assert target.chiamate_create_text_channel[0]["name"] == "chat"
    # Il canale deve ricevere l'OGGETTO categoria appena creato,
    # non quello originale.
    assert target.chiamate_create_text_channel[0]["category"].name == "Generale"


@pytest.mark.asyncio
async def test_canale_testuale_preserva_topic_nsfw_slowmode():
    canale = _FakeTextChannel(
        1, "annunci", position=0, topic="Solo annunci", nsfw=True, slowmode_delay=30
    )
    source = _FakeSourceGuild(categories=[], channels=[canale])
    target = _FakeTargetGuild()

    await clone_categories_and_channels(source, target, role_id_map={})

    chiamata = target.chiamate_create_text_channel[0]
    assert chiamata["topic"] == "Solo annunci"
    assert chiamata["nsfw"] is True
    assert chiamata["slowmode_delay"] == 30


@pytest.mark.asyncio
async def test_canale_vocale_preserva_bitrate_e_user_limit():
    canale = _FakeVoiceChannel(1, "Vocale Gaming", position=0, bitrate=96000, user_limit=5)
    source = _FakeSourceGuild(categories=[], channels=[canale])
    target = _FakeTargetGuild()

    await clone_categories_and_channels(source, target, role_id_map={})

    chiamata = target.chiamate_create_voice_channel[0]
    assert chiamata["bitrate"] == 96000
    assert chiamata["user_limit"] == 5


@pytest.mark.asyncio
async def test_canale_fuori_da_una_categoria_riceve_category_none():
    canale = _FakeTextChannel(1, "generale", position=0, category=None)
    source = _FakeSourceGuild(categories=[], channels=[canale])
    target = _FakeTargetGuild()

    await clone_categories_and_channels(source, target, role_id_map={})

    assert target.chiamate_create_text_channel[0]["category"] is None


@pytest.mark.asyncio
async def test_restituisce_la_mappa_id_di_categorie_e_canali():
    categoria = _FakeCategory(10, "Cat", position=0)
    canale = _FakeTextChannel(20, "chan", position=0, category=categoria)
    source = _FakeSourceGuild(categories=[categoria], channels=[categoria, canale])
    target = _FakeTargetGuild()

    mappa = await clone_categories_and_channels(source, target, role_id_map={})

    assert 10 in mappa
    assert 20 in mappa


@pytest.mark.asyncio
async def test_categorie_e_canali_rispettano_l_ordine_di_posizione():
    cat_b = _FakeCategory(1, "B", position=1)
    cat_a = _FakeCategory(2, "A", position=0)
    source = _FakeSourceGuild(categories=[cat_b, cat_a], channels=[cat_b, cat_a])
    target = _FakeTargetGuild()

    await clone_categories_and_channels(source, target, role_id_map={})

    nomi = [c["name"] for c in target.chiamate_create_category]
    assert nomi == ["A", "B"]
