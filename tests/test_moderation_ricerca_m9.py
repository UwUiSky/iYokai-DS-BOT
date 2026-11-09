"""
tests/test_moderation_ricerca_m9.py
===================================
M9 (#115): ricerca ban (MOD-107), membri con filtri e CSV (MOD-108), invito (MOD-110) e prove di un caso o di
una nota (MOD-038). Logica pura, cog con oggetti finti, database vero per le prove.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.moderation import ricerca
from cogs.moderation._shared import MODULE_ACTIONS, MODULE_CASE_SYSTEM
from cogs.moderation.ricerca import RicercaModerazioneCog
from core import moderation_prove as prove
from core import moderation_ricerca_logic as logica
from core.database import db
from core.immagini_pipeline import EsitoImmagine
from core.repositories.moderation_repo import moderation_repo
from tests.support.discord_fakes import fake_guild, fake_interaction

G = 424242
ORA = datetime(2026, 11, 9, tzinfo=timezone.utc)


def _ban(i, nome="x", motivo=None):
    return SimpleNamespace(user=SimpleNamespace(id=i, name=nome), reason=motivo)


async def _it(voci):
    for v in voci:
        yield v


# ----------------------------------------------------------------- MOD-107
def test_cerca_ban_per_nome_id_e_motivo_con_tetto():
    voci = [logica.VoceBan(i, f"Pippo{i}", "spam" if i % 2 else None) for i in range(1, 60)]
    assert logica.cerca_ban(voci, "PIPPO5")[0][0].user_id == 5
    assert [v.user_id for v in logica.cerca_ban(voci, "7")[0]][:1] == [7]
    trovate, totale = logica.cerca_ban(voci, "spam")
    assert len(trovate) == 25 and totale == 30
    assert logica.cerca_ban(voci, "   ") == ([], 0)


async def test_leggi_ban_cache_di_cinque_minuti_e_tetto():
    logica.svuota_cache()
    voci, troncato = await logica.leggi_ban(1, _it([_ban(1), _ban(2)]), ora=1000.0)
    assert len(voci) == 2 and not troncato
    # dentro i 5 minuti non rilegge (l'iteratore vuoto non cambia niente)
    voci2, _ = await logica.leggi_ban(1, _it([]), ora=1200.0)
    assert len(voci2) == 2
    voci3, _ = await logica.leggi_ban(1, _it([_ban(9)]), ora=1301.0)
    assert [v.user_id for v in voci3] == [9]
    voci4, _ = await logica.leggi_ban(1, _it([_ban(5)]), ora=1302.0, forza=True)
    assert [v.user_id for v in voci4] == [5]
    grandi, troncato = await logica.leggi_ban(2, _it([_ban(i) for i in range(logica.MAX_BAN_LETTI + 5)]), ora=1.0)
    assert len(grandi) == logica.MAX_BAN_LETTI and troncato
    logica.svuota_cache()


def test_suggerimenti_unban_al_massimo_25():
    voci = [logica.VoceBan(i, f"u{i}", None) for i in range(100)]
    assert len(logica.suggerimenti_unban(voci, "")) == 25
    assert [v.user_id for v in logica.suggerimenti_unban(voci, "u99")] == [99]


# ----------------------------------------------------------------- MOD-108
def _m(i, nome="anna", ruoli=(), vocale=False, bot=False, entrato=ORA, creato=ORA - timedelta(days=400)):
    return SimpleNamespace(
        id=i, name=nome, display_name=nome, global_name=None, bot=bot, joined_at=entrato, created_at=creato,
        roles=[SimpleNamespace(id=r) for r in ruoli], voice=object() if vocale else None,
    )


def test_filtri_membri():
    ms = [_m(1, "Anna"), _m(2, "Bruno", ruoli=(7,), vocale=True), _m(3, "BotX", bot=True), _m(4, "nuovo", creato=ORA - timedelta(days=2))]
    f = lambda **k: [m.id for m in logica.filtra_membri(ms, ora=ORA, **k)]
    assert f(nome="anna") == [1] and f(ruolo_id=7) == [2] and f(in_vocale=True) == [2]
    assert f(bot=True) == [3] and f(account_piu_giovane_di=timedelta(days=7)) == [4]
    assert f(nome="re:^(anna|bruno)$") == [1, 2]
    assert f(entrato_dopo=ORA + timedelta(days=1)) == []
    assert f() == [1, 2, 3, 4]


def test_regex_sbagliata_o_troppo_lunga_si_rifiuta():
    with pytest.raises(ValueError):
        logica.compila_nome("re:(")
    with pytest.raises(ValueError):
        logica.compila_nome("re:" + "a" * 101)


def test_csv_non_esegue_formule_e_ha_il_tetto():
    dati, righe = logica.csv_membri([_m(1, "=cmd()"), _m(2, "ok")])
    testo = dati.decode()
    assert "'=cmd()" in testo and righe == 2
    molti = [_m(i) for i in range(logica.MAX_RIGHE_CSV + 10)]
    assert logica.csv_membri(molti)[1] == logica.MAX_RIGHE_CSV


# ----------------------------------------------------------------- MOD-110
def test_codice_invito():
    assert logica.codice_invito("https://discord.gg/abc-123") == "abc-123"
    assert logica.codice_invito("discord.com/invite/XyZ9") == "XyZ9"
    assert logica.codice_invito("abc123") == "abc123"
    assert logica.codice_invito("ciao come va") is None and logica.codice_invito("a") is None


@pytest.fixture
async def amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(G, MODULE_ACTIONS, True)
    await db.set_module_active_for_guild(G, MODULE_CASE_SYSTEM, True)
    logica.svuota_cache()
    yield
    database_module.db._modules_cache.clear()


async def test_cog_cerca_ban_risponde_solo_a_chi_comanda(amb):
    guild = fake_guild(G)
    guild.bans = lambda limit=None: _it([_ban(11, "Spammer", "spam"), _ban(12, "Altro")])
    i = fake_interaction(guild=guild)
    cog = RicercaModerazioneCog(bot=MagicMock())
    await cog.cerca.callback(cog, i, "spam")
    kw = i.followup.send.await_args.kwargs
    assert kw["ephemeral"] is True and "11" in kw["embed"].description and "12" not in kw["embed"].description


async def test_cog_invito_gestisce_invito_inesistente(amb):
    bot = MagicMock()
    bot.fetch_invite = AsyncMock(side_effect=discord.NotFound(MagicMock(status=404, reason="x"), "x"))
    i = fake_interaction(guild=fake_guild(G))
    cog = RicercaModerazioneCog(bot=bot)
    await cog.invito.callback(cog, i, "abc123")
    bot.fetch_invite.assert_awaited_once_with("abc123", with_counts=True, with_expiration=True)
    assert i.followup.send.await_args.kwargs["ephemeral"] is True


async def test_cog_membri_filtro_errato_non_rimanda(amb):
    i = fake_interaction(guild=fake_guild(G))
    cog = RicercaModerazioneCog(bot=MagicMock())
    await cog.membri.callback(cog, i, entrato_dopo="domani!!")
    i.response.send_message.assert_awaited_once()
    i.response.defer.assert_not_awaited()


async def test_completa_ban_chiede_il_livello(amb, monkeypatch):
    monkeypatch.setattr("core.command_access.puo_usare", AsyncMock(return_value=False))
    i = fake_interaction(guild=fake_guild(G))
    assert await ricerca.completa_ban(i, "x") == []


# ----------------------------------------------------------------- MOD-038
def test_tipi_di_prova():
    assert prove.tipo_di("a.PNG") == "immagine" and prove.tipo_di("r.pdf") == "file" and prove.tipo_di("n.txt") == "file"
    assert prove.tipo_di("virus.exe") is None and prove.tipo_di("a.svg") is None
    assert "/" not in prove.nome_sicuro("../../etc/passwd.txt") and len(prove.nome_sicuro("x" * 500)) == 80


async def _agg(nome="p.pdf", dati=b"%PDF-1.4 x", size=None, **k):
    async def leggi():
        return dati

    return await prove.aggiungi_prova(G, 5, 9, nome_file=nome, dimensione=len(dati) if size is None else size, leggi=leggi, **k)


async def test_pdf_si_conserva_grezzo_e_si_elenca(amb):
    e = await _agg(case_number=3)
    assert e.errore is None and e.tipo == "file"
    elenco = await moderation_repo.list_prove(G, case_number=3)
    assert len(elenco) == 1 and elenco[0]["nome_file"] == "p.pdf"
    assert await moderation_repo.list_prove(G, case_number=4) == []


async def test_regole_tipo_peso_e_massimo_cinque(amb):
    assert (await _agg("v.exe", case_number=1)).errore == "prove_tipo"
    assert (await _agg(size=prove.MAX_BYTE + 1, case_number=1)).errore == "prove_grande"
    for _ in range(prove.MAX_PROVE):
        assert (await _agg(case_number=1)).errore is None
    assert (await _agg(case_number=1)).errore == "prove_troppe"
    assert (await _agg(nota_id=1)).errore is None  # la nota ha il suo conto


async def test_immagine_si_tiene_solo_ricodificata(amb, monkeypatch):
    originale, ricodificata = b"ORIGINALE-GIF", b"\x89PNG-ricodificato"
    monkeypatch.setattr(prove.immagini_pipeline, "analizza_immagine", AsyncMock(return_value=EsitoImmagine(png=ricodificata, sha256="s")))
    e = await _agg("a.gif", dati=originale, case_number=2)
    assert e.tipo == "immagine"
    righe = await moderation_repo.get_immagini_prova(G, 2)
    assert righe[0]["dati"] == ricodificata and originale not in righe[0]["dati"]


async def test_immagine_sospetta_o_non_analizzata_non_si_conserva(amb, monkeypatch):
    from core.immagini_byte_logic import SOSPETTA

    for esito in (EsitoImmagine(verdetto=SOSPETTA, png=b"x"), EsitoImmagine(non_analizzata="sandbox_ferma"), EsitoImmagine()):
        monkeypatch.setattr(prove.immagini_pipeline, "analizza_immagine", AsyncMock(return_value=esito))
        assert (await _agg("a.png", dati=b"zz", case_number=8)).errore == "prove_immagine"
    assert await moderation_repo.list_prove(G, case_number=8) == []
