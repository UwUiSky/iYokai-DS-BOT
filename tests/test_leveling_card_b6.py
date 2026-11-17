"""
tests/test_leveling_card_b6.py
==============================
#124 B6 (LIV-031, 051, 054, 055, 056): segnaposto {xp} nell'annuncio, colore di testo e velo sulla
card, sfondo e colore predefiniti del server (anche «auto» dall'icona).
Funzioni coperte: SPEC §15 (catalogo #124)
"""

import io
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from PIL import Image

import cogs.leveling.leveling as modulo
from core.leveling_logic import LevelingSettings, rendi_annuncio
from core.rank_card_image import (
    ALTEZZA,
    LARGHEZZA,
    DatiRankCard,
    colore_medio,
    prepara_sfondo,
    render_rank_card,
)
from core.repositories.leveling_repo import LevelingRepository
from core.repositories.leveling_settings_repo import LevelingSettingsRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

GUILD = 100


def _png(colore, dim=(60, 30)):
    b = io.BytesIO()
    Image.new("RGB", dim, colore).save(b, "PNG")
    return b.getvalue()


# ---------------------------------------------------------------- LIV-031
def test_liv031_il_segnaposto_xp():
    t = rendi_annuncio("{utente} ha {xp} XP al livello {livello}", utente="@u", livello=4, server="S", ruoli_premio=[], xp=1234)
    assert t == "@u ha 1234 XP al livello 4"
    # Un nome di server che contiene un segnaposto non viene sostituito di nuovo.
    assert "{xp}" in rendi_annuncio("{server}", utente="u", livello=1, server="{xp}", ruoli_premio=[], xp=9)


# ---------------------------------------------------------------- LIV-051 e 054
def _dati(**kw):
    return DatiRankCard("Yokai", 3, 10, 100, 130, 1, 5, **kw)


def _pixel(png, x, y):
    return Image.open(io.BytesIO(png)).convert("RGB").getpixel((x, y))


def test_liv051_il_colore_del_testo_cambia_il_nome():
    base = render_rank_card(_dati(), None)
    rosso = render_rank_card(_dati(colore_testo="#FF0000"), None)
    assert base != rosso
    assert Image.open(io.BytesIO(rosso)).size == (LARGHEZZA, ALTEZZA)
    # Un colore non valido non rompe il disegno: vale come non scelto.
    assert render_rank_card(_dati(colore_testo="rosso"), None) == base


def test_liv054_il_velo_decide_quanto_si_vede_lo_sfondo():
    sfondo = prepara_sfondo(_png((250, 20, 20), (800, 360)))
    scoperto = render_rank_card(_dati(velo=0), None, sfondo)
    coperto = render_rank_card(_dati(velo=100), None, sfondo)
    di_base = render_rank_card(_dati(), None, sfondo)
    p0, p100, pb = (_pixel(x, 200, 20) for x in (scoperto, coperto, di_base))
    assert p0[0] > 200  # sfondo rosso ben visibile sotto il pannello
    assert p100 != p0 and p100[0] < 100
    assert p0 != pb != p100
    assert render_rank_card(_dati(velo=500), None, sfondo) == coperto  # fuori scala: tagliato a 100


# ---------------------------------------------------------------- LIV-056
def test_liv056_colore_medio_dell_icona():
    assert colore_medio(_png((200, 100, 50))) == "#C86432"
    assert colore_medio(b"non un'immagine") is None


# ---------------------------------------------------------------- archivio
@pytest.fixture
def repo(clean_db):
    return LevelingRepository(pool_provider=lambda: clean_db)


@pytest.mark.asyncio
async def test_liv051_054_extra_della_card_si_salvano_e_si_azzerano(repo):
    assert await repo.get_card_extra(1) == (None, None)
    await repo.set_card_extra(1, colore_testo="#AABBCC")
    await repo.set_card_extra(1, velo=40)  # cambia solo ciò che si dà
    assert await repo.get_card_extra(1) == ("#AABBCC", 40)
    with pytest.raises(ValueError):
        await repo.set_card_extra(1, velo=101)
    with pytest.raises(ValueError):
        await repo.set_card_extra(1, colore_testo="rosso")
    await repo.reset_rank_card_prefs(1)
    assert await repo.get_card_extra(1) == (None, None)


@pytest.mark.asyncio
async def test_liv055_sfondo_del_server_si_salva_e_si_toglie(repo):
    assert await repo.get_sfondo_server(GUILD) is None
    await repo.set_sfondo_server(GUILD, b"jpeg")
    assert await repo.get_sfondo_server(GUILD) == b"jpeg"
    assert await repo.get_sfondo_server(GUILD + 1) is None
    await repo.set_sfondo_server(GUILD, None)
    assert await repo.get_sfondo_server(GUILD) is None


@pytest.mark.asyncio
async def test_liv056_colore_del_server_valori_ammessi(clean_db):
    s = LevelingSettingsRepository(pool_provider=lambda: clean_db)
    for ok in ("#AABBCC", "auto", ""):
        assert (await s.set_options(GUILD, card_colore=ok)).card_colore == ok
    for no in ("rosso", "#abc", "#GGGGGG", "AUTO"):
        with pytest.raises(ValueError):
            await s.set_options(GUILD, card_colore=no)


# ---------------------------------------------------------------- comando card e colore del server
@pytest.fixture
def cog(monkeypatch, clean_db):
    from tests.support.moduli import attiva_livelli

    return modulo.LevelingCog(bot=None)


@pytest.mark.asyncio
async def test_liv056_colore_del_server_fisso_auto_e_assente(monkeypatch):
    cog = modulo.LevelingCog(bot=None)
    cog.cog_unload()
    guild = MagicMock()
    guild.id = 7
    guild.icon = MagicMock(key="abc")
    guild.icon.read = AsyncMock(return_value=_png((200, 100, 50)))
    assert await cog._colore_server(guild, LevelingSettings(card_colore="#112233")) == "#112233"
    assert await cog._colore_server(guild, LevelingSettings()) is None
    assert await cog._colore_server(guild, LevelingSettings(card_colore="auto")) == "#C86432"
    guild.icon.read.reset_mock()
    assert await cog._colore_server(guild, LevelingSettings(card_colore="auto")) == "#C86432"
    guild.icon.read.assert_not_awaited()  # la seconda volta viene dalla memoria
    guild.icon = None
    assert await cog._colore_server(guild, LevelingSettings(card_colore="auto")) is None


@pytest.mark.asyncio
async def test_liv055_056_il_comando_card_chiede_il_permesso_e_salva(monkeypatch, clean_db):
    from core.repositories.leveling_settings_repo import leveling_settings_repo
    from tests.support.moduli import attiva_livelli

    await attiva_livelli(monkeypatch, clean_db, GUILD)
    for r in (leveling_settings_repo, modulo.leveling_repo):
        monkeypatch.setattr(r, "_pool_provider", lambda: clean_db)
    cog = modulo.LevelingCog(bot=None)
    cog.cog_unload()
    funzione = modulo.LevelingCog.impostazioni_card.callback if hasattr(modulo.LevelingCog.impostazioni_card, "callback") else None
    from core.command_groups import costruisci_gruppi, registra_comandi_del_cog

    cmd = next(c for c in registra_comandi_del_cog(cog, gruppi=costruisci_gruppi(), tree=None) if c.qualified_name == "admin-livelli card")

    senza = fake_interaction(guild=fake_guild(GUILD), user=fake_member(7), permissions=discord.Permissions.none())
    await cmd.callback(cog, senza, None, None, None, "#112233", None)
    assert (await leveling_settings_repo.get_config(GUILD, fresco=True)).impostazioni.card_colore == ""

    inter = fake_interaction(guild=fake_guild(GUILD), user=fake_member(7), permissions=discord.Permissions(manage_guild=True))
    await cmd.callback(cog, inter, None, None, None, "#112233", None)
    assert (await leveling_settings_repo.get_config(GUILD, fresco=True)).impostazioni.card_colore == "#112233"
    await cmd.callback(cog, inter, None, None, None, "ROSSO", None)  # non valido: resta com'era
    assert (await leveling_settings_repo.get_config(GUILD, fresco=True)).impostazioni.card_colore == "#112233"

    allegato = MagicMock(spec=discord.Attachment)
    allegato.size, allegato.content_type = 1000, "image/png"
    allegato.read = AsyncMock(return_value=_png((10, 200, 10), (800, 360)))
    await cmd.callback(cog, inter, None, allegato, None, None, None)
    assert await modulo.leveling_repo.get_sfondo_server(GUILD) is not None
    await cmd.callback(cog, inter, None, None, True, None, True)
    assert await modulo.leveling_repo.get_sfondo_server(GUILD) is None
    assert (await leveling_settings_repo.get_config(GUILD, fresco=True)).impostazioni.card_colore == ""

    grande = MagicMock(spec=discord.Attachment)
    grande.size, grande.content_type = 99_000_000, "image/png"
    await cmd.callback(cog, inter, None, grande, None, None, None)
    assert await modulo.leveling_repo.get_sfondo_server(GUILD) is None  # troppo grande: rifiutata
