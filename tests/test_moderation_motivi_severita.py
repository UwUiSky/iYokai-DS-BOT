"""
tests/test_moderation_motivi_severita.py
========================================
D68 (#115): motivi pronti con severità e sanzione di base. Elenco preimpostato seminato alla prima lettura del
server, modificabile; la sanzione proposta si legge dal motivo. Database vero.
"""

import pytest

from core import moderation_motivi as motivi
from core.database import db
from core.repositories.moderation_repo import moderation_repo

G = 7_000_000_000_000_001
G2 = 7_000_000_000_000_002


@pytest.fixture(autouse=True)
async def _amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    motivi._cache.clear()
    motivi._seminati.clear()
    yield
    motivi._cache.clear()
    motivi._seminati.clear()


def test_l_elenco_preimpostato_rispetta_i_limiti():
    assert 8 <= len(motivi.PREIMPOSTATI) <= motivi.MAX_MOTIVI
    nomi = [m["nome"].casefold() for m in motivi.PREIMPOSTATI]
    assert len(set(nomi)) == len(nomi)
    for m in motivi.PREIMPOSTATI:
        assert 1 <= len(m["nome"]) <= motivi.MAX_NOME
        assert motivi.MIN_TESTO <= len(m["testo"]) <= motivi.MAX_TESTO
        assert m["severita"] in motivi.SEVERITA and m["azione"] in motivi.AZIONI
        assert (m["durata_s"] is not None) == (m["azione"] == "timeout")
        assert m["durata_s"] is None or 0 < m["durata_s"] <= motivi.MAX_TIMEOUT_S


def test_ogni_severita_ha_almeno_un_motivo_e_gravissima_banna():
    per = {s: [m for m in motivi.PREIMPOSTATI if m["severita"] == s] for s in motivi.SEVERITA}
    assert all(per.values())
    assert {m["azione"] for m in per["gravissima"]} == {"ban"}
    assert {m["azione"] for m in per["lieve"]} == {"warn"}
    nomi = " ".join(m["nome"].casefold() for m in motivi.PREIMPOSTATI)
    for parola in ("spam", "insulti", "nsfw", "raid", "phishing", "pubblicit", "flood", "molestie"):
        assert parola in nomi


async def test_alla_prima_lettura_il_server_riceve_i_motivi_pronti():
    elenco = await motivi.elenco(G)
    assert {m["nome"] for m in elenco} == {m["nome"] for m in motivi.PREIMPOSTATI}
    spam = next(m for m in elenco if m["nome"].casefold() == "spam")
    assert spam["severita"] == "lieve" and spam["azione"] == "warn" and spam["durata_s"] is None


async def test_un_motivo_tolto_non_ritorna_alla_lettura_dopo():
    await motivi.elenco(G)
    assert await motivi.togli(G, "Spam") is True
    motivi._seminati.clear()  # riavvio del bot: la cache in memoria è vuota
    motivi._cache.clear()
    assert "spam" not in [m["nome"].casefold() for m in await motivi.elenco(G)]


async def test_la_semina_e_per_server_e_non_si_ripete():
    await motivi.elenco(G)
    await motivi.elenco(G2)
    assert await moderation_repo.count_motivi(G) == len(motivi.PREIMPOSTATI)
    motivi._seminati.clear()
    motivi._cache.clear()
    await motivi.elenco(G)
    assert await moderation_repo.count_motivi(G) == len(motivi.PREIMPOSTATI)


async def test_semina_che_fallisce_non_segna_il_server_come_caricato(monkeypatch):
    async def rotta(*a, **k):
        raise RuntimeError("db")

    monkeypatch.setattr(moderation_repo, "semina_motivi", rotta)
    with pytest.raises(RuntimeError):
        await motivi.elenco(G)
    assert G not in motivi._seminati


async def test_aggiungi_con_sanzione_e_proposta():
    await motivi.elenco(G)
    i = await motivi.aggiungi(G, "Bestemmie", "Bestemmie in chat", 10, severita="media", azione="timeout", durata_s=7200)
    p = await motivi.proposta(G, f"#m{i}")
    assert p == motivi.Proposta(severita="media", azione="timeout", durata_s=7200)
    assert await motivi.proposta(G, "scritto a mano") is None
    assert await motivi.proposta(G, "#m999999") is None


@pytest.mark.parametrize(
    "extra,codice",
    [
        ({"severita": "enorme"}, "severita"),
        ({"azione": "esilio"}, "azione"),
        ({"azione": "warn", "durata_s": 60}, "durata"),
        ({"azione": "timeout", "durata_s": motivi.MAX_TIMEOUT_S + 1}, "durata"),
        ({"azione": "timeout", "durata_s": 0}, "durata"),
    ],
)
async def test_aggiungi_rifiuta_sanzioni_non_valide(extra, codice):
    await motivi.elenco(G)
    await motivi.togli(G, "Spam")
    with pytest.raises(ValueError, match=codice):
        await motivi.aggiungi(G, "x", "motivo valido", 10, **extra)


async def test_modifica_cambia_solo_quello_che_si_passa():
    await motivi.elenco(G)
    assert await motivi.modifica(G, "SPAM", severita="media", azione="timeout", durata_s=3600) is True
    spam = next(m for m in await motivi.elenco(G) if m["nome"].casefold() == "spam")
    assert (spam["severita"], spam["azione"], spam["durata_s"]) == ("media", "timeout", 3600)
    assert spam["testo"]  # il testo non si è perso
    # cambiare azione in kick toglie la durata
    assert await motivi.modifica(G, "spam", azione="kick") is True
    spam = next(m for m in await motivi.elenco(G) if m["nome"].casefold() == "spam")
    assert spam["azione"] == "kick" and spam["durata_s"] is None
    assert await motivi.modifica(G, "non esiste", severita="lieve") is False


async def test_etichetta_mostra_la_sanzione_entro_100_caratteri():
    m = {"id": 3, "nome": "Spam", "testo": "x" * 400, "severita": "media", "azione": "timeout", "durata_s": 3600}
    e = motivi.etichetta(m)
    assert len(e) <= 100 and "timeout" in e and "1h" in e
    assert motivi.etichetta({"id": 4, "nome": "Vecchio", "testo": "abc", "severita": None, "azione": None, "durata_s": None}) == "Vecchio: abc"


# --- comandi: aggiungi/modifica e /mod-sanzioni applica ---

from unittest.mock import AsyncMock, MagicMock

from cogs.moderation._shared import MODULE_ACTIONS, MODULE_CASE_SYSTEM, SETTING_MOD_LOG_CHANNEL
from cogs.moderation.actions import ModerationActionsCog
from cogs.moderation.case_system import ModerationCaseSystemCog
from cogs.moderation.motivo_pronto import ModerationMotivoProntoCog, ModuloDurata, VistaProposta
from tests.test_moderation_ordine_azione import ID_BERSAGLIO, ID_CANALE_LOG, ID_MODERATORE, ID_SERVER, Scena


@pytest.fixture
async def server_pronto():
    g = ID_SERVER
    await db.set_module_active_for_guild(g, MODULE_ACTIONS, True)
    await db.set_module_active_for_guild(g, MODULE_CASE_SYSTEM, True)
    await db.set_guild_setting(g, SETTING_MOD_LOG_CHANNEL, ID_CANALE_LOG)
    motivi._seminati.discard(g)
    yield g
    db._modules_cache.clear()


@pytest.fixture(autouse=True)
def _livello(monkeypatch):
    """Di base chi comanda ha anche il livello di /mod-ban; i test sul livello lo tolgono."""
    import cogs.moderation.motivo_pronto as mp

    livelli = AsyncMock(return_value=True)
    monkeypatch.setattr(mp, "puo_usare", livelli)
    return livelli


def _scelta(valore):
    import discord
    from discord import app_commands

    return app_commands.Choice(name=valore, value=valore)


def _gestione(scena):
    scena.moderatore.guild_permissions.manage_guild = True


async def test_aggiungi_con_severita_azione_e_durata(server_pronto):
    scena = Scena()
    _gestione(scena)
    cog = ModerationCaseSystemCog(bot=None)
    await cog.motivo_aggiungi.callback(cog, scena.interazione, "Bestemmie", "Bestemmie in chat", _scelta("media"), _scelta("timeout"), "2h")
    m = await moderation_repo.get_motivo(server_pronto, "bestemmie")
    assert (m["severita"], m["azione"], m["durata_s"]) == ("media", "timeout", 7200)


async def test_aggiungi_con_durata_su_un_warn_e_rifiutato(server_pronto):
    scena = Scena()
    _gestione(scena)
    cog = ModerationCaseSystemCog(bot=None)
    await cog.motivo_aggiungi.callback(cog, scena.interazione, "Strano", "motivo valido", None, _scelta("warn"), "2h")
    assert await moderation_repo.get_motivo(server_pronto, "strano") is None
    scena.interazione.response.send_message.assert_called_once()


async def test_modifica_da_comando(server_pronto):
    scena = Scena()
    _gestione(scena)
    cog = ModerationCaseSystemCog(bot=None)
    await motivi.elenco(server_pronto)
    await cog.motivo_modifica.callback(cog, scena.interazione, "Insulti", None, _scelta("grave"), _scelta("timeout"), "1d")
    m = await moderation_repo.get_motivo(server_pronto, "insulti")
    assert (m["severita"], m["azione"], m["durata_s"]) == ("grave", "timeout", 86400)


def _vista_da(scena, risposta):
    return risposta.call_args.kwargs["view"]


async def _applica(scena, nome_motivo):
    motivo = next(m for m in await motivi.elenco(ID_SERVER) if m["nome"] == nome_motivo)
    cog = ModerationMotivoProntoCog(bot=None)
    await cog.applica.callback(cog, scena.interazione, scena.bersaglio, f"#m{motivo['id']}")
    return _vista_da(scena, scena.interazione.response.send_message), motivo


async def test_applica_propone_la_sanzione_del_motivo(server_pronto):
    scena = Scena()
    vista, _ = await _applica(scena, "Insulti")
    assert (vista.azione, vista.durata_s, vista.severita) == ("timeout", 3600, "media")
    assert scena.interazione.response.send_message.call_args.kwargs["ephemeral"] is True
    assert scena.bersaglio.timeout.call_count == 0  # niente prima della conferma
    assert await moderation_repo.list_cases_for_user(server_pronto, ID_BERSAGLIO) == []


async def test_applica_senza_motivo_pronto_non_propone(server_pronto):
    scena = Scena()
    cog = ModerationMotivoProntoCog(bot=None)
    await cog.applica.callback(cog, scena.interazione, scena.bersaglio, "scritto a mano")
    assert "view" not in scena.interazione.response.send_message.call_args.kwargs


async def test_conferma_esegue_il_timeout_proposto(server_pronto):
    scena = Scena()
    vista, motivo = await _applica(scena, "Insulti")
    scena.interazione.client.get_cog.return_value = ModerationActionsCog(bot=None)
    scena.interazione.response.send_message.reset_mock()
    await vista.conferma.callback(scena.interazione)
    scena.bersaglio.timeout.assert_awaited_once()
    assert scena.bersaglio.timeout.call_args.args[0].total_seconds() == 3600
    casi = await moderation_repo.list_cases_for_user(server_pronto, ID_BERSAGLIO)
    assert len(casi) == 1 and casi[0].action_type == "timeout" and casi[0].reason == motivo["testo"]


async def test_lo_staff_cambia_azione_e_durata_prima_di_confermare(server_pronto):
    scena = Scena()
    vista, motivo = await _applica(scena, "Insulti")
    vista.menu._values = ["kick"]
    scena.interazione.response.edit_message = AsyncMock()
    await vista._cambia_azione(scena.interazione)
    assert vista.azione == "kick" and vista.durata_s is None and vista.bottone_durata.disabled is True
    vista.menu._values = ["timeout"]
    await vista._cambia_azione(scena.interazione)
    assert vista.azione == "timeout" and vista.bottone_durata.disabled is False
    modulo = ModuloDurata(vista, "t", "c")
    modulo.durata._value = "6h"
    await modulo.on_submit(scena.interazione)
    assert vista.durata_s == 6 * 3600
    modulo.durata._value = "29d"
    scena.interazione.response.send_message.reset_mock()
    await modulo.on_submit(scena.interazione)
    assert vista.durata_s == 6 * 3600
    scena.interazione.response.send_message.assert_called_once()


async def test_doppio_clic_su_conferma_non_ripete(server_pronto):
    scena = Scena()
    vista, _ = await _applica(scena, "Spam")
    scena.interazione.client.get_cog.return_value = ModerationActionsCog(bot=None)
    await vista.conferma.callback(scena.interazione)
    await vista.conferma.callback(scena.interazione)
    assert len(await moderation_repo.list_cases_for_user(server_pronto, ID_BERSAGLIO)) == 1


async def test_un_altro_utente_non_usa_i_tasti(server_pronto):
    scena = Scena()
    vista, _ = await _applica(scena, "Spam")
    altro = MagicMock()
    altro.user.id = 4242
    altro.response.send_message = AsyncMock()
    assert await vista.interaction_check(altro) is False


async def test_chi_non_ha_il_livello_modban_non_vede_kick_e_ban(server_pronto, _livello):
    _livello.return_value = False
    scena = Scena()
    vista, _ = await _applica(scena, "Insulti")
    assert {o.value for o in vista.menu.options} == {"warn", "timeout"}


async def test_motivo_con_kick_o_ban_e_rifiutato_senza_livello_modban(server_pronto, _livello):
    _livello.return_value = False
    scena = Scena()
    motivo = next(m for m in await motivi.elenco(ID_SERVER) if m["nome"] == "Raid")
    cog = ModerationMotivoProntoCog(bot=None)
    await cog.applica.callback(cog, scena.interazione, scena.bersaglio, f"#m{motivo['id']}")
    assert "view" not in scena.interazione.response.send_message.call_args.kwargs
    assert scena.bersaglio.ban.call_count == 0


async def test_il_livello_si_ricontrolla_alla_conferma(server_pronto, _livello):
    scena = Scena()
    vista, _ = await _applica(scena, "Insulti")
    vista.azione = "ban"  # come se il menu fosse stato manomesso
    _livello.return_value = False
    scena.interazione.response.send_message.reset_mock()
    await vista.conferma.callback(scena.interazione)
    assert scena.bersaglio.ban.call_count == 0
    scena.interazione.response.send_message.assert_called_once()


async def test_il_livello_mod_si_ricontrolla_alla_conferma_anche_per_timeout(server_pronto, _livello):
    """Chi perde il ruolo Mod mentre la proposta è aperta non dà più nemmeno un timeout."""
    scena = Scena()
    vista, _ = await _applica(scena, "Insulti")
    scena.interazione.client.get_cog.return_value = ModerationActionsCog(bot=None)
    _livello.return_value = False
    scena.interazione.response.send_message.reset_mock()
    await vista.conferma.callback(scena.interazione)
    assert scena.bersaglio.timeout.call_count == 0
    assert await moderation_repo.list_cases_for_user(server_pronto, ID_BERSAGLIO) == []
    scena.interazione.response.send_message.assert_called_once()


async def test_doppio_clic_insieme_su_un_kick_non_ripete(server_pronto, _livello):
    """Due clic che arrivano insieme: il controllo del livello attende, ma la sanzione parte una volta sola."""
    import asyncio

    async def lento(*_a, **_k):
        await asyncio.sleep(0)
        return True

    _livello.side_effect = lento
    scena = Scena()
    vista, _ = await _applica(scena, "Evasione sanzione")
    scena.interazione.client.get_cog.return_value = ModerationActionsCog(bot=None)
    await asyncio.gather(vista.conferma.callback(scena.interazione), vista.conferma.callback(scena.interazione))
    assert scena.bersaglio.kick.call_count <= 1
    assert len(await moderation_repo.list_cases_for_user(server_pronto, ID_BERSAGLIO)) <= 1
