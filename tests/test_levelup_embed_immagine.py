"""
tests/test_levelup_embed_immagine.py
====================================
Annuncio del level-up dentro un embed salvato (LIV-032) e con una piccola card allegata (LIV-033).
Funzioni coperte: catalogo #124
"""

import io
from unittest.mock import AsyncMock

import pytest
from PIL import Image

import cogs.leveling.leveling as modulo
from core import embed_builder_logic as eb
from core.rank_card_image import ALTEZZA_LEVELUP, LARGHEZZA, render_levelup_card
from core.repositories.saved_embed_repo import saved_embed_repo
from tests.test_leveling_premi_b2 import GUILD, _lancia, annuncio, premi, prova, scena  # noqa: F401  (fixture)


def test_la_card_del_levelup_e_un_png_della_misura_giusta():
    png = render_levelup_card("Nome " * 40, 12345, None)
    immagine = Image.open(io.BytesIO(png))
    assert immagine.format == "PNG" and immagine.size == (LARGHEZZA, ALTEZZA_LEVELUP)
    assert Image.open(io.BytesIO(render_levelup_card("x", 1, b"non e un'immagine", "#zzz", "tema-che-non-c-e"))).size == immagine.size


@pytest.mark.asyncio
async def test_annuncio_con_embed_e_immagine(annuncio, monkeypatch, clean_db):
    cog, guild, membro, premi, canale = annuncio
    monkeypatch.setattr(saved_embed_repo, "_pool_provider", lambda: clean_db, raising=False)
    salvato = type("S", (), {"data": {"title": "Livello {livello}", "description": "{utente} su {server}"}})()
    monkeypatch.setattr(saved_embed_repo, "get", AsyncMock(return_value=salvato))
    monkeypatch.setattr(cog, "_xp_totale", AsyncMock(return_value=0))
    membro.display_avatar.read = AsyncMock(return_value=b"")
    imp = modulo.LevelingSettings(levelup_embed="mio", levelup_immagine=True)
    await cog._annuncia_level_up(membro, guild, canale, 7, imp, None)
    kw = canale.send.await_args.kwargs
    assert kw["embed"].title == "Livello 7" and kw["file"].filename == "level-up.png"
    assert kw["embed"].image.url == "attachment://level-up.png"


@pytest.mark.asyncio
async def test_embed_mancante_o_immagine_rotta_non_fermano_l_annuncio(annuncio, monkeypatch):
    cog, guild, membro, premi, canale = annuncio
    monkeypatch.setattr(saved_embed_repo, "get", AsyncMock(return_value=None))
    monkeypatch.setattr(modulo, "run_image_task", AsyncMock(side_effect=RuntimeError("boom")))
    membro.display_avatar.read = AsyncMock(return_value=b"")
    imp = modulo.LevelingSettings(levelup_embed="sparito", levelup_immagine=True)
    await cog._annuncia_level_up(membro, guild, canale, 3, imp, None)
    kw = canale.send.await_args.kwargs
    assert "embed" not in kw and "file" not in kw and "livello **3**" in canale.send.await_args.args[0]


@pytest.mark.asyncio
async def test_il_comando_salva_embed_e_immagine_e_rifiuta_un_nome_sconosciuto(prova, monkeypatch):
    cog, inter, canale, repo = prova
    monkeypatch.setattr(saved_embed_repo, "get", AsyncMock(return_value=None))
    await _lancia(cog, inter, embed="nonesiste")
    assert (await repo.get_config(GUILD, fresco=True)).impostazioni.levelup_embed == ""
    monkeypatch.setattr(saved_embed_repo, "get", AsyncMock(return_value=object()))
    await _lancia(cog, inter, embed="mio", immagine=True)
    i = (await repo.get_config(GUILD, fresco=True)).impostazioni
    assert (i.levelup_embed, i.levelup_immagine) == ("mio", True)
    await _lancia(cog, inter, embed="-")
    assert (await repo.get_config(GUILD, fresco=True)).impostazioni.levelup_embed == ""


@pytest.mark.asyncio
async def test_carta_globale_somma_tutti_i_server(clean_db, monkeypatch):
    """LIV-089: la card usa XP e monete di tutti i server, e solo quelli positivi."""
    from cogs.leveling import progressi
    from core.repositories.progressi_repo import ProgressiRepository
    from tests.support.discord_fakes import fake_member

    for g, xp, coin in ((1, 100, 5), (2, 50, 7), (3, -40, -9)):
        await clean_db.execute("INSERT INTO leveling_totals (guild_id, user_id, xp_total, coins_total, level) VALUES ($1, 9, $2, $3, 0)", g, xp, coin)
    repo = ProgressiRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(progressi.servizio, "progressi_repo", repo)
    monkeypatch.setattr(progressi, "leveling_repo", type("L", (), {"get_sfondo_card": AsyncMock(return_value=None)})())
    assert await repo.monete_globali(9) == 12 and (await repo.xp_globale(9))[0] == 150
    membro = fake_member(9, "Globale")
    membro.display_avatar.read = AsyncMock(return_value=b"")
    png = await progressi.carta_globale(membro)
    assert Image.open(io.BytesIO(png)).format == "PNG"
