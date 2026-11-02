"""
tests/test_automod_liste.py
===========================
Liste con nome (tetti, liste di sistema), pannello delle liste, modelli pronti e regole personali sul testo
nel motore (Solo YouTube, parolacce, sole parole permesse, evento modifica).
Funzioni coperte: SPEC §6 (AMD-011, 012, 015, 016, 025, 028), D63
"""

from unittest.mock import AsyncMock

import pytest

import core.automod_liste_pannello as PL
from core import automod_liste_service as S
from core import automod_modelli as MOD
from core import automod_regole_service as regole
from core.automod_regole_logic import Regola, RegolaNonValida, azioni_da_json
from core.repositories.automod_liste_repo import automod_liste_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member
from tests.test_automod_regole_filtri import GUILD_ID, _msg, cog  # noqa: F401  (fixture)


@pytest.fixture
def db_liste(clean_db, monkeypatch):
    monkeypatch.setattr(automod_liste_repo, "_pool_provider", lambda: clean_db)
    S.svuota_cache()
    return clean_db


def test_leggi_voci_senza_doppioni_con_tetti():
    assert S.leggi_voci("Uno\nuno, due\n\n  tre ") == ("Uno", "due", "tre")
    with pytest.raises(RegolaNonValida):
        S.leggi_voci("x" * 61)
    with pytest.raises(RegolaNonValida):
        S.leggi_voci("\n".join(str(i) for i in range(1001)))
    assert len(S.leggi_voci("\n".join(str(i) for i in range(1000)))) == 1000


def test_liste_di_sistema_esistono_e_non_sono_vuote():
    for nome, (tipo, _) in S.LISTE_DI_SISTEMA.items():
        t, voci = S.lista_di_sistema(nome)
        assert t == tipo and len(voci) >= 10 and all(not v.startswith("#") for v in voci)
    assert "discord.me" in S.lista_di_sistema("@vetrine-inviti")[1]


async def test_salva_aggiungi_togli_elimina_e_tetti(db_liste):
    await S.salva_lista(1, "link", "domini", ("a.com",))
    assert await S.aggiungi_voci(1, "link", ("B.com", "a.com")) == ("a.com", "B.com")
    assert await S.togli_voci(1, "link", ("A.COM",)) == ("B.com",)
    for nome in ("@sistema", "", "x" * 33):
        with pytest.raises(RegolaNonValida):
            await S.salva_lista(1, nome, "parole", ())
    with pytest.raises(RegolaNonValida):
        await S.salva_lista(1, "ok", "altro", ())
    for i in range(19):
        await S.salva_lista(1, f"l{i}", "parole", ())
    with pytest.raises(RegolaNonValida):
        await S.salva_lista(1, "una-di-troppo", "parole", ())  # 21esima
    await S.salva_lista(1, "link", "domini", ("x.com",))  # una esistente si può riscrivere
    await S.salva_lista(2, "link", "parole", ())  # un altro server ha le sue
    assert await S.elimina_lista(1, "link") and not await S.elimina_lista(1, "link")
    assert "link" not in await S.voci_per_regole(1) and "@parolacce-it" in await S.voci_per_regole(1)


def test_modelli_pronti_sono_regole_valide():
    from core.automod_regole_logic import regola_a_json, regola_da_json

    for m in MOD.MODELLI:
        r = MOD.modello(m, "Nome " + m)
        assert regola_da_json(regola_a_json(r)).innesco == r.innesco


# ---------------------------------------------------------------- pannello

def _vista():
    inter = fake_interaction(guild=fake_guild(guild_id=GUILD_ID))
    inter.user = fake_member(user_id=5)
    return PL.PannelloListe(inter, "it")


async def test_pannello_liste_forma_entro_i_limiti(db_liste):
    for i in range(20):
        await S.salva_lista(GUILD_ID, f"{'n' * 29}{i:03d}", "parole", tuple(f"{'v' * 60}{j}"[:60] for j in range(1000)))
    vista = _vista()
    await vista.carica()
    for scelta in (None, "@parolacce-it", f"{'n' * 29}000"):
        vista.scelta = scelta
        embed = vista.schermata()
        righe = vista.to_components()
        assert len(righe) <= 5 and all(len(r["components"]) <= 5 for r in righe)
        assert len(embed) <= 6000
        for c in righe[0]["components"]:
            assert len(c.get("options", [])) <= 25
        assert all(len(c.get("label", "")) <= 45 for r in righe for c in r["components"])
    vista.scelta = "@parolacce-it"
    vista.schermata()
    assert all(b.disabled for b in vista.children if getattr(b, "custom_id", "") in ("am:l:agg", "am:l:togli", "am:l:elimina"))


async def test_pannello_liste_non_tocca_quelle_di_sistema_e_usa_solo_il_proprietario(db_liste, monkeypatch):
    from unittest.mock import AsyncMock

    from core import ui_base

    monkeypatch.setattr(ui_base, "_utente_o_server_in_blacklist", AsyncMock(return_value=False))
    vista = _vista()
    await vista.carica()
    assert await vista.interaction_check(fake_interaction(user=fake_member(user_id=5)))
    assert not await vista.interaction_check(fake_interaction(user=fake_member(user_id=6)))
    inter = fake_interaction(guild=fake_guild(guild_id=GUILD_ID))
    inter.response.edit_message = AsyncMock()
    vista.scelta = "@parolacce-it"
    await vista._elimina(inter)
    vista.elimina_armato = True
    await S.salva_lista(GUILD_ID, "mia", "parole", ("ciao",))
    vista.scelta = "mia"
    await vista._elimina(inter)
    assert "mia" not in await S.liste_del_server(GUILD_ID)


# ---------------------------------------------------------------- motore

async def _personale(innesco, **kw):
    return await regole.crea_personale(
        GUILD_ID, Regola(chiave="x", tipo="personale", nome="Mia regola", innesco=innesco,
                         azioni=azioni_da_json([{"t": "cancella"}]), **kw), 1)


async def test_solo_youtube_cancella_gli_altri_link(cog):
    await _personale(MOD.modello("solo_youtube", "Solo YT").innesco)
    ok, no = _msg("guarda https://youtu.be/abc"), _msg("guarda https://vimeo.com/1")
    await cog.on_message(ok)
    await cog.on_message(no)
    ok.delete.assert_not_awaited()
    no.delete.assert_awaited_once()


async def test_parolacce_di_sistema_e_log_col_nome_della_regola(cog, clean_db):
    await _personale(MOD.modello("parolacce", "Parolacce").innesco)
    m = _msg("che merda di giornata")
    await cog.on_message(m)
    m.delete.assert_awaited_once()
    riga = await clean_db.fetchrow("SELECT violation FROM automod_action_log")
    assert riga["violation"].startswith("p:")


async def test_lista_del_server_e_regola_spenta(cog, db_liste):
    await S.salva_lista(GUILD_ID, "vietate", "parole", ("zucchino",))
    r = await _personale({"tipo": "lista", "liste": ["vietate"]})
    m1 = _msg("un bello zucchino")
    await cog.on_message(m1)
    m1.delete.assert_awaited_once()
    from dataclasses import replace

    await regole.salva(GUILD_ID, replace(r, attiva=False), 1)
    m2 = _msg("un bello zucchino")
    await cog.on_message(m2)
    m2.delete.assert_not_awaited()


async def test_sole_parole_permesse_e_evento_modifica(cog):
    await _personale({"tipo": "solo_permesse", "parole": ["sì", "no"]})
    ok, no = _msg("sì no"), _msg("sì forse")
    await cog.on_message(ok)
    await cog.on_message(no)
    ok.delete.assert_not_awaited()
    no.delete.assert_awaited_once()
    # una regola solo per le modifiche non scatta sul messaggio nuovo
    await regole.elimina(GUILD_ID, (await regole.regole_del_server(GUILD_ID))[0].chiave)
    await _personale({"tipo": "regex", "regex": ["vietato"]}, evento="modifica")
    nuovo = _msg("vietato")
    await cog.on_message(nuovo)
    nuovo.delete.assert_not_awaited()


async def test_account_nuovi_senza_link_solo_per_gli_account_giovani(cog):
    from datetime import datetime, timedelta, timezone

    await _personale(MOD.modello("account_nuovi", "No link").innesco, condizioni=MOD.modello("account_nuovi", "x").condizioni)
    adesso = datetime.now(timezone.utc)
    giovane, vecchio = _msg("vedi https://x.it", creato=adesso - timedelta(days=1)), _msg("vedi https://x.it", creato=adesso - timedelta(days=900))
    await cog.on_message(giovane)
    await cog.on_message(vecchio)
    giovane.delete.assert_awaited_once()
    vecchio.delete.assert_not_awaited()
