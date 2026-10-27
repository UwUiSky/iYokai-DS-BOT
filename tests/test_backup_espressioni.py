"""
tests/test_backup_espressioni.py
================================
Emoji, sticker e suoni del backup: niente doppioni per nome, limite che
conta i presenti, permesso «Creare espressioni», tetto suoni per boost.
Funzioni coperte: SPEC §11.5–§11.7
"""

from types import SimpleNamespace

import pytest

from core.backup_clone_logic import (
    RiepilogoCopia,
    clone_emoji,
    clone_soundboard,
    clone_stickers,
    tetto_suoni,
)


class _Elemento:
    def __init__(self, name, animated=False):
        self.name = name
        self.animated = animated
        self.description = ""
        self.emoji = None
        self.volume = 1.0

    async def read(self):
        return b"x"


class _Dest:
    def __init__(self, emojis=(), stickers=(), suoni=(), tier=0, permesso=True, admin=False):
        self.emojis = list(emojis)
        self.stickers = list(stickers)
        self.soundboard_sounds = list(suoni)
        self.emoji_limit = 3
        self.sticker_limit = 2
        self.premium_tier = tier
        self.me = SimpleNamespace(
            guild_permissions=SimpleNamespace(create_expressions=permesso, administrator=admin)
        )
        self.creati = []

    async def create_custom_emoji(self, **kw):
        self.creati.append(("emoji", kw["name"]))

    async def create_sticker(self, **kw):
        self.creati.append(("sticker", kw["name"]))

    async def create_soundboard_sound(self, **kw):
        self.creati.append(("suono", kw["name"]))


def _src(**kw):
    return SimpleNamespace(
        emojis=kw.get("emojis", []), stickers=kw.get("stickers", []), soundboard_sounds=kw.get("suoni", [])
    )


@pytest.mark.asyncio
async def test_emoji_senza_doppioni_per_nome():
    dest = _Dest(emojis=[_Elemento("a")])
    saltate = await clone_emoji(_src(emojis=[_Elemento("a"), _Elemento("b")]), dest)
    assert dest.creati == [("emoji", "b")]
    assert saltate == 0


@pytest.mark.asyncio
async def test_emoji_limite_conta_i_presenti():
    dest = _Dest(emojis=[_Elemento("p1"), _Elemento("p2")])  # limite 3, 2 presenti
    saltate = await clone_emoji(_src(emojis=[_Elemento("a"), _Elemento("b")]), dest)
    assert [n for _, n in dest.creati] == ["a"]
    assert saltate == 1


@pytest.mark.asyncio
async def test_emoji_senza_permesso_non_prova_e_lo_dice():
    dest = _Dest(permesso=False)
    r = RiepilogoCopia()
    saltate = await clone_emoji(_src(emojis=[_Elemento("a")]), dest, r)
    assert dest.creati == []
    assert saltate == 1
    assert r.espressioni_senza_permesso is True


@pytest.mark.asyncio
async def test_amministratore_non_ha_bisogno_del_permesso():
    dest = _Dest(permesso=False, admin=True)
    await clone_emoji(_src(emojis=[_Elemento("a")]), dest)
    assert dest.creati == [("emoji", "a")]


@pytest.mark.asyncio
async def test_sticker_senza_doppioni_e_limite():
    dest = _Dest(stickers=[_Elemento("s0")])
    saltati = await clone_stickers(_src(stickers=[_Elemento("s0"), _Elemento("s1"), _Elemento("s2")]), dest)
    assert [n for _, n in dest.creati] == ["s1"]
    assert saltati == 1


@pytest.mark.asyncio
async def test_sticker_senza_permesso():
    r = RiepilogoCopia()
    dest = _Dest(permesso=False)
    assert await clone_stickers(_src(stickers=[_Elemento("s")]), dest, r) == 1
    assert dest.creati == [] and r.espressioni_senza_permesso


def test_tetto_suoni_per_boost():
    assert [tetto_suoni(t) for t in range(4)] == [8, 24, 36, 48]
    assert tetto_suoni(9) == 48


@pytest.mark.asyncio
async def test_suoni_tetto_per_boost_e_presenti():
    suoni = [_Elemento(f"n{i}") for i in range(10)]
    dest = _Dest(suoni=[_Elemento("n0")], tier=0)
    saltati = await clone_soundboard(_src(suoni=suoni), dest)
    assert len(dest.creati) == 7  # 8 meno 1 presente; n0 non si ripete
    assert saltati == 2
    dest2 = _Dest(tier=1)
    assert await clone_soundboard(_src(suoni=suoni), dest2) == 0


@pytest.mark.asyncio
async def test_suoni_senza_permesso():
    r = RiepilogoCopia()
    dest = _Dest(permesso=False)
    assert await clone_soundboard(_src(suoni=[_Elemento("n")]), dest, r) == 1
    assert dest.creati == []


def test_riassunto_dice_il_permesso_mancante():
    from core.backup_orchestrator import riassunto_copia

    r = RiepilogoCopia(espressioni_senza_permesso=True, emoji_saltate=3)
    testo = riassunto_copia(r)
    assert "Creare espressioni" in testo
    assert "oltre i limiti" not in testo
