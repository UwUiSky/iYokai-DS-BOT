"""
tests/test_moderation_opzioni_comandi_m5.py
===========================================
Opzioni dei comandi di moderazione, blocco M5 (#115): giorni di messaggi nel tempban (MOD-009), messaggi
cancellati al kick (MOD-011), DM sì/no nel comando (MOD-058), motivo facoltativo o obbligatorio (MOD-065),
motivi pronti (MOD-113) e completamento sul motivo (MOD-116). Database vero.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.moderation import _shared
from cogs.moderation._shared import MODULE_ACTIONS, MODULE_CASE_SYSTEM, SETTING_MOD_LOG_CHANNEL
from cogs.moderation.actions import ModerationActionsCog
from cogs.moderation.case_system import ModerationCaseSystemCog
from cogs.moderation.softban_mute import ModerationSoftbanMuteCog
from core import moderation_motivi as motivi
from core import moderation_opzioni
from core.database import db
from core.repositories.moderation_repo import moderation_repo
from tests.support.discord_fakes import fake_text_channel
from tests.test_moderation_ordine_azione import ID_BERSAGLIO, ID_CANALE_LOG, ID_MODERATORE, ID_SERVER, Scena

G = ID_SERVER


@pytest.fixture(autouse=True)
async def _amb(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    motivi._cache.clear()
    motivi._seminati.add(G)  # l'elenco di base (D68) ha un suo test: qui si parte da un server senza motivi
    await db.set_module_active_for_guild(G, MODULE_ACTIONS, True)
    await db.set_module_active_for_guild(G, MODULE_CASE_SYSTEM, True)
    await db.set_guild_setting(G, SETTING_MOD_LOG_CHANNEL, ID_CANALE_LOG)
    yield
    database_module.db._modules_cache.clear()
    motivi._cache.clear()
    motivi._seminati.clear()


def _testo(scena):
    c = scena.interazione.response.send_message.call_args
    return c.args[0] if c.args else c.kwargs.get("content", "")


# --- logica dei motivi pronti ---

@pytest.mark.parametrize("valore,atteso", [("#m12", 12), ("#m1", 1), ("#12", None), ("ciao", None), ("#m", None), ("#mx", None), ("#m0", None)])
def test_id_dal_valore(valore, atteso):
    assert motivi.id_da_valore(valore) == atteso


def test_suggerimenti_filtrano_e_hanno_il_tetto():
    elenco = [{"id": i, "nome": f"motivo{i}", "testo": "x" * 400} for i in range(1, 31)]
    tutti = motivi.suggerimenti(elenco, "")
    assert len(tutti) == 25
    for nome, valore in tutti:
        assert len(nome) <= 100 and len(valore) <= 100 and valore.startswith("#m")
    assert motivi.suggerimenti(elenco, "MOTIVO7") == [(motivi.etichetta(elenco[6]), "#m7")]
    assert motivi.suggerimenti(elenco, "zzz") == []


async def test_aggiungi_elenca_e_togli():
    nuovo = await motivi.aggiungi(G, "spam", "Spam o pubblicità non richiesta", 10)
    assert nuovo > 0
    assert [m["nome"] for m in await motivi.elenco(G)] == ["spam"]
    assert await motivi.togli(G, "SPAM") is True
    assert await motivi.elenco(G) == []
    assert await motivi.togli(G, "spam") is False


@pytest.mark.parametrize("nome,testo", [("", "motivo valido"), ("x" * 33, "motivo valido"), ("ok", "no"), ("ok", "x" * 513)])
async def test_aggiungi_rifiuta_valori_fuori_limite(nome, testo):
    with pytest.raises(ValueError):
        await motivi.aggiungi(G, nome, testo, 10)


async def test_nome_doppio_e_tetto_di_25():
    await motivi.aggiungi(G, "uno", "primo motivo", 10)
    with pytest.raises(ValueError):
        await motivi.aggiungi(G, "UNO", "altro motivo", 10)
    for i in range(24):
        await motivi.aggiungi(G, f"m{i}", "motivo numero", 10)
    with pytest.raises(ValueError):
        await motivi.aggiungi(G, "uno-di-troppo", "motivo numero", 10)


async def test_espandi_motivo_pronto_e_testo_libero():
    i = await motivi.aggiungi(G, "spam", "Spam o pubblicità non richiesta", 10)
    assert await motivi.espandi(G, f"#m{i}") == "Spam o pubblicità non richiesta"
    assert await motivi.espandi(G, "#m999") == "#m999"
    assert await motivi.espandi(G, "scritto a mano") == "scritto a mano"


async def test_la_cache_si_aggiorna_dopo_un_nuovo_motivo():
    assert await motivi.elenco(G) == []
    await motivi.aggiungi(G, "uno", "primo motivo", 10)
    assert len(await motivi.elenco(G)) == 1


# --- motivo facoltativo o obbligatorio ---

async def test_il_motivo_e_obbligatorio_di_base():
    assert (await moderation_opzioni.leggi(G)).motivo_obbligatorio is True


async def test_warn_senza_motivo_con_server_obbligatorio_e_rifiutato():
    scena = Scena()
    cog = ModerationActionsCog(bot=None)
    await cog.warn.callback(cog, scena.interazione, scena.bersaglio)
    assert await moderation_repo.list_cases_for_user(G, ID_BERSAGLIO) == []
    assert "motivo" in _testo(scena).lower()


async def test_warn_senza_motivo_con_server_facoltativo_usa_il_testo_di_base():
    await moderation_opzioni.imposta_motivo_obbligatorio(G, False, ID_MODERATORE)
    scena = Scena()
    cog = ModerationActionsCog(bot=None)
    await cog.warn.callback(cog, scena.interazione, scena.bersaglio)
    casi = await moderation_repo.list_cases_for_user(G, ID_BERSAGLIO)
    assert len(casi) == 1 and casi[0].reason == _shared.MOTIVO_NON_INDICATO


async def test_il_motivo_pronto_si_espande_nel_caso():
    i = await motivi.aggiungi(G, "spam", "Spam o pubblicità non richiesta", 10)
    scena = Scena()
    cog = ModerationActionsCog(bot=None)
    await cog.warn.callback(cog, scena.interazione, scena.bersaglio, f"#m{i}")
    casi = await moderation_repo.list_cases_for_user(G, ID_BERSAGLIO)
    assert casi[0].reason == "Spam o pubblicità non richiesta"


async def test_cambiare_il_motivo_di_un_caso_resta_obbligatorio():
    await moderation_opzioni.imposta_motivo_obbligatorio(G, False, ID_MODERATORE)
    scena = Scena()
    n = await moderation_repo.create_case(G, ID_BERSAGLIO, ID_MODERATORE, "warn", "vecchio motivo")
    cog = ModerationCaseSystemCog(bot=None)
    await cog.case_reason.callback(cog, scena.interazione, n, None)
    assert (await moderation_repo.get_case(G, n)).reason == "vecchio motivo"


@pytest.mark.parametrize("nome", ["warn", "kick", "ban", "tempban", "unban", "timeout", "softban", "mute_role", "unmute_role"])
def test_il_motivo_e_facoltativo_nella_firma(nome):
    import inspect

    for classe in (ModerationActionsCog, ModerationSoftbanMuteCog):
        cmd = getattr(classe, nome, None)
        if cmd is not None:
            p = inspect.signature(cmd.callback).parameters["reason"]
            assert p.default is None
            return
    raise AssertionError(nome)


# --- DM nel comando ---

async def test_dm_false_nel_warn_non_manda_il_messaggio():
    scena = Scena()
    cog = ModerationActionsCog(bot=None)
    await cog.warn.callback(cog, scena.interazione, scena.bersaglio, "motivo valido", False)
    scena.bersaglio.send.assert_not_called()
    assert len(await moderation_repo.list_cases_for_user(G, ID_BERSAGLIO)) == 1


async def test_dm_true_vince_sul_server_che_l_ha_spento():
    await moderation_opzioni.imposta_dm(G, "warn", False, ID_MODERATORE)
    scena = Scena()
    cog = ModerationActionsCog(bot=None)
    await cog.warn.callback(cog, scena.interazione, scena.bersaglio, "motivo valido", True)
    scena.bersaglio.send.assert_called_once()


async def test_dm_vuoto_segue_il_server():
    await moderation_opzioni.imposta_dm(G, "warn", False, ID_MODERATORE)
    scena = Scena()
    cog = ModerationActionsCog(bot=None)
    await cog.warn.callback(cog, scena.interazione, scena.bersaglio, "motivo valido")
    scena.bersaglio.send.assert_not_called()


async def test_dm_false_nel_kick():
    scena = Scena()
    cog = ModerationActionsCog(bot=None)
    await cog.kick.callback(cog, scena.interazione, scena.bersaglio, "motivo valido", None, False)
    scena.bersaglio.send.assert_not_called()
    scena.bersaglio.kick.assert_called_once()


# --- tempban: giorni di messaggi ---

async def test_tempban_cancella_i_giorni_scelti():
    scena = Scena()
    cog = ModerationActionsCog(bot=None)
    await cog.tempban.callback(cog, scena.interazione, scena.bersaglio, "7d", "motivo valido", "fuori", 3)
    assert scena.bersaglio.ban.call_args.kwargs["delete_message_seconds"] == 3 * 86400


async def test_tempban_senza_giorni_usa_il_valore_del_server():
    await moderation_opzioni.imposta_giorni_ban(G, 2, ID_MODERATORE)
    scena = Scena()
    cog = ModerationActionsCog(bot=None)
    await cog.tempban.callback(cog, scena.interazione, scena.bersaglio, "7d", "motivo valido")
    assert scena.bersaglio.ban.call_args.kwargs["delete_message_seconds"] == 2 * 86400


# --- kick: cancella gli ultimi messaggi ---

def _canale_con_messaggi(scena, autori):
    canale = fake_text_channel(55, "chat")
    messaggi = []
    for i, a in enumerate(autori):
        m = MagicMock(spec=discord.Message)
        m.author = MagicMock(id=a)
        m.id = 1000 + i
        m.delete = AsyncMock()
        messaggi.append(m)

    async def _storia(limit=None, after=None, **kw):
        for m in messaggi[:limit]:
            yield m

    canale.history = _storia
    canale.delete_messages = AsyncMock()
    canale.permissions_for = MagicMock(return_value=discord.Permissions(manage_messages=True, read_message_history=True, view_channel=True))
    scena.interazione.channel = canale
    return canale, messaggi


async def test_kick_cancella_gli_ultimi_messaggi_solo_del_membro():
    scena = Scena()
    canale, messaggi = _canale_con_messaggi(scena, [ID_BERSAGLIO, 1, ID_BERSAGLIO, ID_BERSAGLIO, ID_BERSAGLIO])
    cog = ModerationActionsCog(bot=None)
    await cog.kick.callback(cog, scena.interazione, scena.bersaglio, "motivo valido", 3)
    cancellati = canale.delete_messages.call_args.args[0]
    assert [m.id for m in cancellati] == [1000, 1002, 1003]
    scena.bersaglio.kick.assert_called_once()


async def test_kick_senza_permesso_di_cancellare_non_espelle():
    scena = Scena()
    canale, _ = _canale_con_messaggi(scena, [ID_BERSAGLIO])
    canale.permissions_for = MagicMock(return_value=discord.Permissions(manage_messages=False, view_channel=True))
    cog = ModerationActionsCog(bot=None)
    await cog.kick.callback(cog, scena.interazione, scena.bersaglio, "motivo valido", 3)
    scena.bersaglio.kick.assert_not_called()


async def test_kick_fallito_non_cancella_nulla():
    scena = Scena()
    canale, _ = _canale_con_messaggi(scena, [ID_BERSAGLIO, ID_BERSAGLIO])
    scena.bersaglio.kick.side_effect = discord.HTTPException(MagicMock(status=400, reason="x"), "x")
    cog = ModerationActionsCog(bot=None)
    await cog.kick.callback(cog, scena.interazione, scena.bersaglio, "motivo valido", 2)
    canale.delete_messages.assert_not_called()


# --- comandi dei motivi pronti ---

async def test_motivi_aggiungi_elenco_togli():
    scena = Scena()
    scena.moderatore.guild_permissions = discord.Permissions(manage_guild=True)
    cog = ModerationCaseSystemCog(bot=None)
    await cog.motivo_aggiungi.callback(cog, scena.interazione, "spam", "Spam o pubblicità non richiesta")
    assert [m["nome"] for m in await motivi.elenco(G)] == ["spam"]
    scena.interazione.response.send_message.reset_mock()
    await cog.motivo_elenco.callback(cog, scena.interazione)
    assert "spam" in scena.interazione.response.send_message.call_args.kwargs["embed"].description
    scena.interazione.response.send_message.reset_mock()
    await cog.motivo_togli.callback(cog, scena.interazione, "spam")
    assert await motivi.elenco(G) == []


async def test_motivi_aggiungi_senza_manage_guild_e_rifiutato():
    scena = Scena()
    scena.moderatore.guild_permissions = discord.Permissions(moderate_members=True)
    cog = ModerationCaseSystemCog(bot=None)
    await cog.motivo_aggiungi.callback(cog, scena.interazione, "spam", "Spam o pubblicità non richiesta")
    assert await motivi.elenco(G) == []


async def test_completamento_del_motivo():
    await motivi.aggiungi(G, "spam", "Spam o pubblicità non richiesta", 10)
    scena = Scena()
    scelte = await _shared.completa_motivo(scena.interazione, "sp")
    assert [(s.name[:4], s.value) for s in scelte][0][1].startswith("#m")
    assert await _shared.completa_motivo(scena.interazione, "zzz") == []
