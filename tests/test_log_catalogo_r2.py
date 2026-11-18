"""
tests/test_log_catalogo_r2.py
=============================
Catalogo log (#119), giro r2log. LOG-010 e LOG-011 le scrive il codice di moderazione nel log di
moderazione (M 1.8): qui si controlla che le prove restino al loro posto.
"""

import importlib

import pytest

PROVE_MODERAZIONE = {
    # LOG-010: scadenza di tempban e mute a ruolo, fine di un lock a tempo
    "tests.test_moderation_tempban_modi": ["test_la_scadenza_scrive_nel_log_di_moderazione"],
    # LOG-011: lock, unlock, slowmode e clear lasciano una riga con chi ha dato il comando
    "tests.test_moderation_clear_filtri": ["test_lock_unlock_slowmode_lasciano_una_riga_di_log", "test_clear_filtra_e_scrive_nel_log"],
}


@pytest.mark.parametrize("modulo", sorted(PROVE_MODERAZIONE))
def test_log010_log011_le_prove_della_moderazione_esistono_ancora(modulo):
    corpo = importlib.import_module(modulo)
    for nome in PROVE_MODERAZIONE[modulo]:
        assert callable(getattr(corpo, nome, None)), f"{modulo}.{nome} e' sparito: LOG-010/LOG-011 non sono piu' provati"


# ================================================================== LOG-016 e LOG-026
from unittest.mock import AsyncMock, MagicMock  # noqa: E402

import discord  # noqa: E402

import cogs.logging.log_config as config  # noqa: E402
import core.channel_router as router  # noqa: E402
from core import log_personalizza  # noqa: E402
from core.log_eventi_logic import INTERRUTTORI  # noqa: E402
from core.log_personalizza_logic import (  # noqa: E402
    FORMATO_MAX,
    applica_formato,
    nome_segnaposto,
    segnaposto_da_embed,
)
from core.repositories.log_personalizza_repo import LogPersonalizzaRepository  # noqa: E402
from core.repositories.output_channel_repo import OutputChannelRepository  # noqa: E402
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_text_channel  # noqa: E402

SERVER = 910
ALTRO_SERVER = 911


@pytest.fixture
def repo(clean_db, monkeypatch):
    r = LogPersonalizzaRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(config, "log_personalizza_repo", r)
    monkeypatch.setattr(log_personalizza, "log_personalizza_repo", r)
    monkeypatch.setattr(router, "output_channel_repo", OutputChannelRepository(pool_provider=lambda: clean_db))
    return r


def _embed():
    e = discord.Embed(title="Messaggio cancellato", description="ciao", timestamp=discord.utils.utcnow())
    e.add_field(name="Autore", value="<@42> (42)", inline=True)
    e.add_field(name="ID messaggio", value="70", inline=True)
    return e


# ---------------------------------------------------------------- LOG-026: logica
def test_log026_i_segnaposto_hanno_solo_lettere_minuscole_e_trattini_bassi():
    assert nome_segnaposto("ID messaggio") == "id_messaggio"
    assert nome_segnaposto("Più recente!") == "piu_recente"
    assert nome_segnaposto("123") == ""


def test_log026_il_testo_del_server_prende_i_valori_dall_embed_e_toglie_le_righe():
    e = _embed()
    assert applica_formato(e, "{autore} ha perso il messaggio {id_messaggio}: {descrizione} ({titolo}) {inesistente}", "f")
    assert e.description == "<@42> (42) ha perso il messaggio 70: ciao (Messaggio cancellato) {inesistente}"
    assert len(e.fields) == 0 and e.title == "Messaggio cancellato"


def test_log026_la_data_segue_il_formato_scelto():
    e = _embed()
    assert segnaposto_da_embed(e, "R")["data"].endswith(":R>")
    assert segnaposto_da_embed(e, "D")["data"].endswith(":D>")
    assert segnaposto_da_embed(e, "x")["data"].endswith(":f>")  # formato sconosciuto: quello di base


def test_log026_una_specifica_di_str_format_non_viene_valutata_e_il_testo_resta_entro_il_limite():
    e = _embed()
    applica_formato(e, "{autore:>999999999} {descrizione.__class__}" + "x" * 5000, "f")
    assert "{autore:>999999999}" in e.description and len(e.description) <= 2000
    lungo = discord.Embed(title="t", description="d" * 4000)
    applica_formato(lungo, "{descrizione}{descrizione}", "f")
    assert len(lungo.description) <= 4096


def test_log026_un_risultato_vuoto_lascia_l_embed_com_era():
    e = _embed()
    assert not applica_formato(e, "{niente}   ".replace("{niente}", ""), "f")
    assert e.description == "ciao" and len(e.fields) == 2


def test_log026_il_testo_del_comando_ha_un_massimo_di_300_caratteri():
    note = config.LogConfigCog.formato.callback.__annotations__
    assert FORMATO_MAX == 300 and "300" in str(note["testo"]) or "FORMATO_MAX" in str(note["testo"])


# ---------------------------------------------------------------- repository (database vero)
async def test_log016_log026_rotte_e_formati_si_salvano_si_rileggono_e_stanno_nel_loro_server(repo):
    await repo.imposta_rotta(SERVER, "ban", 5)
    await repo.imposta_formato(SERVER, "ban", "{utente} bannato", "R")
    assert (await repo.carica(SERVER)).rotte == {"ban": 5}
    assert (await repo.carica(SERVER)).formati == {"ban": ("{utente} bannato", "R")}
    altro = await repo.carica(ALTRO_SERVER)
    assert altro.rotte == {} and altro.formati == {}
    await repo.imposta_rotta(SERVER, "ban", 6)  # una sola riga per evento
    assert (await repo.carica(SERVER)).rotte == {"ban": 6}
    assert await repo.togli_rotta(SERVER, "ban") and not await repo.togli_rotta(SERVER, "ban")
    assert await repo.togli_formato(SERVER, "ban")
    assert (await repo.carica(SERVER)).rotte == {} and (await repo.carica(SERVER)).formati == {}


async def test_log016_log026_il_repository_rifiuta_valori_fuori_elenco(repo):
    with pytest.raises(ValueError):
        await repo.imposta_rotta(SERVER, "inventato", 5)
    with pytest.raises(ValueError):
        await repo.imposta_formato(SERVER, "ban", "x", "Z")
    with pytest.raises(ValueError):
        await repo.imposta_formato(SERVER, "ban", "x" * (FORMATO_MAX + 1), "f")
    with pytest.raises(ValueError):
        await repo.imposta_formato(SERVER, "ban", "", "f")
    assert (await repo.carica(SERVER)).rotte == {}


async def test_log016_un_nome_nel_database_fuori_elenco_viene_ignorato(repo, clean_db):
    await clean_db.execute("INSERT INTO log_rotte (guild_id, interruttore, channel_id) VALUES ($1, 'vecchio', 1)", SERVER)
    assert (await repo.carica(SERVER)).rotte == {}


# ---------------------------------------------------------------- servizio
def _server_con(canale=None):
    server = fake_guild(guild_id=SERVER)
    server.get_channel = MagicMock(side_effect=lambda cid: canale if canale is not None and canale.id == cid else None)
    return server


async def test_log016_la_rotta_manda_l_evento_nel_canale_scelto_e_non_in_quello_del_gruppo(repo, monkeypatch):
    scelto = fake_text_channel(77)
    monkeypatch.setattr(router, "destinazione_rotta", AsyncMock(return_value=scelto))
    await repo.imposta_rotta(SERVER, "ban", 77)
    base = fake_text_channel(1)
    dest, tipo = await log_personalizza.personalizza(_server_con(scelto), "eventi", "member_ban", base, _embed())
    assert dest is scelto and tipo == "rotta_ban"
    # un altro evento dello stesso gruppo resta dov'era
    dest, tipo = await log_personalizza.personalizza(_server_con(scelto), "eventi", "member_join", base, _embed())
    assert dest is base and tipo == "eventi"


async def test_log016_un_evento_con_piu_nomi_segue_il_suo_interruttore(repo, monkeypatch):
    scelto = fake_text_channel(77)
    monkeypatch.setattr(router, "destinazione_rotta", AsyncMock(return_value=scelto))
    await repo.imposta_rotta(SERVER, "ban", 77)  # «Ban e sban»: member_ban e member_unban
    base = fake_text_channel(1)
    dest, _ = await log_personalizza.personalizza(_server_con(scelto), "eventi", "member_unban", base, _embed())
    assert dest is scelto


async def test_log016_canale_sparito_o_di_un_altro_server_o_non_di_testo_torna_al_gruppo(repo):
    base = fake_text_channel(1)
    await repo.imposta_rotta(SERVER, "ban", 77)
    server = _server_con(None)  # get_channel non lo conosce: canale cancellato o di un altro server
    dest, tipo = await log_personalizza.personalizza(server, "eventi", "member_ban", base, _embed())
    assert dest is base and tipo == "eventi"
    forum = MagicMock(spec=discord.ForumChannel)
    forum.id = 77
    server = _server_con(forum)
    assert await router.destinazione_rotta(server, 77) is None  # un forum non è una rotta
    nascosto = fake_text_channel(77, name=router.NOME_CANALE_NASCOSTO)
    assert await router.destinazione_rotta(_server_con(nascosto), 77) is None


async def test_log016_un_errore_di_lettura_lascia_uscire_il_log_dove_andava(repo, monkeypatch):
    monkeypatch.setattr(repo, "carica", AsyncMock(side_effect=RuntimeError("database giu'")))
    base, e = fake_text_channel(1), _embed()
    dest, tipo = await log_personalizza.personalizza(_server_con(), "eventi", "member_ban", base, e)
    assert dest is base and tipo == "eventi" and len(e.fields) == 2


async def test_log026_il_formato_cambia_l_embed_e_un_evento_senza_interruttore_no(repo):
    await repo.imposta_formato(SERVER, "ban", "Bannato: {autore}", "f")
    e = _embed()
    await log_personalizza.personalizza(_server_con(), "eventi", "member_ban", fake_text_channel(1), e)
    assert e.description == "Bannato: <@42> (42)" and not e.fields
    altro = _embed()
    await log_personalizza.personalizza(_server_con(), "eventi", "member_join", fake_text_channel(1), altro)
    assert altro.description == "ciao"
    senza_chiave = _embed()
    await log_personalizza.personalizza(_server_con(), "eventi", "evento_che_non_ha_interruttore", fake_text_channel(1), senza_chiave)
    assert senza_chiave.description == "ciao"


# ---------------------------------------------------------------- comandi
class _Db:
    def __init__(self, generale):
        self.generale = generale

    async def get_guild_setting(self, guild_id, key):
        return self.generale


def _canale_di(server, canale_id=88, permessi=None):
    c = fake_text_channel(canale_id, "log-ban")
    c.guild = server
    c.permissions_for = MagicMock(return_value=permessi or discord.Permissions(view_channel=True, send_messages=True, embed_links=True))
    return c


async def test_log016_comando_rotta_imposta_toglie_e_rifiuta(repo, monkeypatch):
    monkeypatch.setattr(config, "db", _Db(generale=1))
    cog = config.LogConfigCog(bot=None)
    server = fake_guild(guild_id=SERVER)
    ix = fake_interaction(guild=server)
    canale = _canale_di(server)
    await cog.rotta.callback(cog, ix, "ban", canale)
    assert (await repo.carica(SERVER)).rotte == {"ban": 88}
    assert "<#88>" in ix.response.send_message.call_args.args[0]
    await cog.rotta.callback(cog, ix, "ban", None)
    assert (await repo.carica(SERVER)).rotte == {}
    await cog.rotta.callback(cog, ix, "ban", None)  # niente da togliere: lo dice
    await cog.rotta.callback(cog, ix, "inventato", canale)
    assert (await repo.carica(SERVER)).rotte == {}
    # un canale di un altro server non entra
    altro = _canale_di(fake_guild(guild_id=ALTRO_SERVER))
    await cog.rotta.callback(cog, ix, "ban", altro)
    assert (await repo.carica(SERVER)).rotte == {}
    # senza i permessi del bot non entra
    senza = _canale_di(server, permessi=discord.Permissions(view_channel=True))
    await cog.rotta.callback(cog, ix, "ban", senza)
    assert (await repo.carica(SERVER)).rotte == {}
    assert "send_messages" in ix.response.send_message.call_args.args[0]


async def test_log016_comando_rotta_senza_canale_dei_log_non_salva(repo, monkeypatch):
    monkeypatch.setattr(config, "db", _Db(generale=None))
    cog = config.LogConfigCog(bot=None)
    server = fake_guild(guild_id=SERVER)
    ix = fake_interaction(guild=server)
    await cog.rotta.callback(cog, ix, "ban", _canale_di(server))
    assert (await repo.carica(SERVER)).rotte == {}
    assert "/admin-log canale" in ix.response.send_message.call_args.args[0]


async def test_log026_comando_formato_imposta_e_toglie(repo):
    cog = config.LogConfigCog(bot=None)
    ix = fake_interaction(guild=fake_guild(guild_id=SERVER))
    await cog.formato.callback(cog, ix, "message_delete" if False else "messaggi_cancellati", "{autore}: {descrizione}", "R")
    assert (await repo.carica(SERVER)).formati == {"messaggi_cancellati": ("{autore}: {descrizione}", "R")}
    assert "{titolo}" in ix.response.send_message.call_args.args[0]  # i segnaposto si mostrano com'e'
    await cog.formato.callback(cog, ix, "messaggi_cancellati", None, "f")
    assert (await repo.carica(SERVER)).formati == {}
    await cog.formato.callback(cog, ix, "inventato", "x", "f")
    await cog.formato.callback(cog, ix, "messaggi_cancellati", "x", "Z")
    assert (await repo.carica(SERVER)).formati == {}


def test_log016_log026_le_scelte_dei_comandi_stanno_nei_limiti_di_discord():
    assert len(config.SCELTE_EVENTO) == len(INTERRUTTORI) <= 25
    assert all(len(c.name) <= 100 and len(c.value) <= 100 for c in config.SCELTE_EVENTO)
    assert len(config.SCELTE_DATA) <= 25
