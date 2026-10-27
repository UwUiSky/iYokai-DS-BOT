"""
tests/test_backup_clone_forum_stage.py
======================================
Forum (con etichette) e stage nella copia; canali presenti allineati
cambiando solo i campi diversi; canale spostato di categoria senza doppioni.
Funzioni coperte: SPEC §11.4
"""

from __future__ import annotations

import discord
import pytest

from core.backup_clone_logic import RiepilogoCopia, clone_categories_and_channels


class _Tag:
    def __init__(self, name, moderated=False, emoji=None):
        self.name, self.moderated, self.emoji = name, moderated, emoji


class _Forum(discord.ForumChannel):
    def __init__(self, ch_id, name, position=0, category=None, tags=(), topic="", overwrites=None):
        self.id, self.name, self.position = ch_id, name, position
        self._cat, self._tags = category, list(tags)
        self.topic, self.nsfw, self.slowmode_delay = topic, False, 0
        self._ow = overwrites or {}
        self.modifiche: list[dict] = []

    @property
    def category(self):
        return self._cat

    @property
    def overwrites(self):
        return self._ow

    @property
    def available_tags(self):
        return self._tags

    async def edit(self, **kw):
        self.modifiche.append(kw)


class _Stage(discord.StageChannel):
    def __init__(self, ch_id, name, position=0, category=None):
        self.id, self.name, self.position = ch_id, name, position
        self._cat = category
        self.bitrate, self.user_limit = 64000, 0
        self.modifiche: list[dict] = []

    @property
    def category(self):
        return self._cat

    @property
    def overwrites(self):
        return {}

    async def edit(self, **kw):
        self.modifiche.append(kw)


class _Cat(discord.CategoryChannel):
    def __init__(self, cat_id, name, position=0):
        self.id, self.name, self.position = cat_id, name, position

    @property
    def overwrites(self):
        return {}

    async def edit(self, **kw):
        pass


class _Sorgente:
    def __init__(self, canali, categorie=()):
        self.channels = [*categorie, *canali]
        self.categories = list(categorie)


class _Creato:
    def __init__(self, i, nome):
        self.id, self.name = i, nome


class _Dest:
    bitrate_limit = 96000.0

    def __init__(self, canali=(), categorie=()):
        self.channels = [*categorie, *canali]
        self.categories = list(categorie)
        self.default_role = None
        self.create_calls: list[tuple[str, dict]] = []
        self._id = 9000

    async def _crea(self, tipo, kw):
        self.create_calls.append((tipo, kw))
        self._id += 1
        return _Creato(self._id, kw["name"])

    async def create_category(self, **kw):
        return await self._crea("categoria", kw)

    async def create_forum(self, **kw):
        return await self._crea("forum", kw)

    async def create_stage_channel(self, **kw):
        return await self._crea("stage", kw)

    async def create_text_channel(self, **kw):
        return await self._crea("testo", kw)

    async def create_voice_channel(self, **kw):
        return await self._crea("voce", kw)


@pytest.mark.asyncio
async def test_forum_e_stage_si_creano_con_etichette():
    forum = _Forum(1, "idee", tags=[_Tag("bug", True), _Tag("novità")], topic="Proposte")
    stage = _Stage(2, "Assemblea")
    dest = _Dest()
    mappa = await clone_categories_and_channels(_Sorgente([forum, stage]), dest, {})
    tipi = dict((t, kw) for t, kw in dest.create_calls)
    assert set(tipi) == {"forum", "stage"}
    assert [(t.name, t.moderated) for t in tipi["forum"]["available_tags"]] == [("bug", True), ("novità", False)]
    assert tipi["forum"]["topic"] == "Proposte"
    assert tipi["stage"]["bitrate"] == 64000
    assert set(mappa) == {1, 2}


@pytest.mark.asyncio
async def test_canale_uguale_non_viene_modificato():
    forum = _Forum(1, "idee", tags=[_Tag("bug")])
    gia = _Forum(50, "idee", tags=[_Tag("bug")])
    dest = _Dest([gia])
    r = RiepilogoCopia()
    mappa = await clone_categories_and_channels(_Sorgente([forum]), dest, {}, r)
    assert mappa == {1: 50}
    assert gia.modifiche == [] and dest.create_calls == []
    assert r.canali_riusati == 1


@pytest.mark.asyncio
async def test_si_cambiano_solo_i_campi_diversi():
    forum = _Forum(1, "idee", tags=[_Tag("bug"), _Tag("nuova")], topic="Nuovo")
    gia = _Forum(50, "idee", tags=[_Tag("bug")], topic="Nuovo")
    await clone_categories_and_channels(_Sorgente([forum]), _Dest([gia]), {})
    assert len(gia.modifiche) == 1
    assert set(gia.modifiche[0]) == {"available_tags", "reason"}


@pytest.mark.asyncio
async def test_canale_spostato_di_categoria_non_si_duplica():
    cat_a, cat_b = _Cat(10, "A"), _Cat(11, "B")
    stage = _Stage(2, "Assemblea", category=cat_b)
    cat_dest_a, cat_dest_b = _Cat(60, "A"), _Cat(61, "B")
    gia = _Stage(70, "Assemblea", category=cat_dest_a)  # nel server di backup stava in A
    dest = _Dest([gia], [cat_dest_a, cat_dest_b])
    mappa = await clone_categories_and_channels(_Sorgente([stage], [cat_a, cat_b]), dest, {})
    assert mappa[2] == 70
    assert [t for t, _ in dest.create_calls] == []
    assert gia.modifiche and gia.modifiche[0]["category"] is cat_dest_b
