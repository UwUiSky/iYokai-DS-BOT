"""
tests/test_tag_extra_r2utl.py
=============================
Catalogo #128, giro r2utl: coda del testo (UTL-003), nomi alternativi (UTL-009), divieti (UTL-014), pausa per utente,
canale o server (UTL-012), scheda e testo grezzo (UTL-007, UTL-008), risposta nel canale scelto con ping (UTL-038).
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.utility.custom_commands as modulo
import cogs.utility.tag_extra as extra
from cogs.utility.custom_commands import CustomCommandsCog
from core.custom_command_logic import vietato_a
from core.repositories.custom_command_repo import CustomCommandRepository, MAX_ALIAS, MAX_VIETATI
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role, fake_text_channel


@pytest.fixture
def repo(clean_db):
    return CustomCommandRepository(pool_provider=lambda: clean_db)


async def _crea(repo, guild=1, nome="regole", **kw):
    campi = dict(response="Testo", use_embed=False, role_id=None, role_action="nessuna", cooldown_seconds=0,
                 ping_ruoli=True, created_by=7)
    campi.update(kw)
    return await repo.create_tag(guild, nome, **campi)


@pytest.mark.asyncio
async def test_utl_003_in_coda_aggiunge_senza_riscrivere_e_rispetta_il_tetto(repo):
    """UTL-003: il testo si aggiunge in fondo; oltre 4000 caratteri non cambia nulla; il ping non si guadagna."""
    await _crea(repo, response="Uno", ping_ruoli=True)
    assert await repo.aggiungi_in_coda(1, "regole", " due", ping_ruoli=False) is True
    tag = await repo.get_tag(1, "regole")
    assert tag.response == "Uno due" and tag.ping_ruoli is False
    await _crea(repo, nome="altro", response="x", ping_ruoli=False)
    assert await repo.aggiungi_in_coda(1, "altro", " y", ping_ruoli=True) is True
    assert (await repo.get_tag(1, "altro")).ping_ruoli is False  # chi aggiunge non dà un permesso che il tag non aveva
    assert await repo.aggiungi_in_coda(1, "altro", "z" * 4000, ping_ruoli=False) is False
    assert (await repo.get_tag(1, "altro")).response == "x y"
    assert await repo.aggiungi_in_coda(1, "manca", "a", ping_ruoli=False) is False
    assert await repo.aggiungi_in_coda(2, "regole", "a", ping_ruoli=False) is False  # un altro server


# CFG-015
@pytest.mark.asyncio
async def test_utl_009_alias_chiama_il_tag_e_ha_un_tetto(repo):
    """UTL-009: fino a 3 nomi alternativi per tag, mai uguali a un tag o a un altro alias, per server."""
    await _crea(repo)
    await _crea(repo, nome="altro")
    assert await repo.aggiungi_alias(1, "regole", "r") == "ok"
    assert await repo.aggiungi_alias(1, "regole", "r") == "occupato"
    assert await repo.aggiungi_alias(1, "regole", "altro") == "occupato"
    assert await repo.aggiungi_alias(1, "manca", "m") == "tag_manca"
    assert await repo.aggiungi_alias(1, "regole", "r2") == "ok"
    assert await repo.aggiungi_alias(1, "regole", "r3") == "ok"
    assert await repo.aggiungi_alias(1, "regole", "r4") == "pieno" and MAX_ALIAS == 3
    assert (await repo.get_tag_o_alias(1, "r2")).name == "regole"
    assert (await repo.get_tag_o_alias(1, "regole")).name == "regole"
    assert await repo.get_tag_o_alias(2, "r2") is None
    assert await repo.alias_di(1, "regole") == ["r", "r2", "r3"]
    assert await repo.togli_alias(1, "r2") is True and await repo.togli_alias(1, "r2") is False
    await repo.delete_tag(1, "regole")
    assert await repo.get_tag_o_alias(1, "r") is None  # eliminato il tag, spariscono gli alias


@pytest.mark.asyncio
async def test_utl_014_divieti_con_tetto_e_controllo(repo):
    """UTL-014: ruoli, canali e utenti vietati (10 per elenco); chi è vietato non usa il tag, nemmeno da un thread."""
    await _crea(repo)
    assert await repo.cambia_divieto(1, "regole", "ruolo", 10, True) == [10]
    assert await repo.cambia_divieto(1, "regole", "ruolo", 10, True) == [10]  # niente doppioni
    for i in range(20, 20 + MAX_VIETATI):
        await repo.cambia_divieto(1, "regole", "canale", i, True)
    assert len((await repo.get_tag(1, "regole")).canali_vietati) == MAX_VIETATI
    assert await repo.cambia_divieto(1, "regole", "utente", 5, True) == [5]
    assert await repo.cambia_divieto(1, "regole", "utente", 5, False) == []
    assert await repo.cambia_divieto(1, "manca", "utente", 5, True) is None
    tag = await repo.get_tag(1, "regole")
    membro = SimpleNamespace(id=1, roles=[SimpleNamespace(id=10)])
    assert vietato_a(tag, membro, SimpleNamespace(id=1)) == "tag_vietato_ruolo"
    assert vietato_a(tag, SimpleNamespace(id=1, roles=[]), SimpleNamespace(id=1, parent_id=20)) == "tag_vietato_canale"
    assert vietato_a(tag, SimpleNamespace(id=1, roles=[]), SimpleNamespace(id=1)) is None


def _tag(**kw):
    base = dict(guild_id=1, name="regole", response="Ciao", use_embed=False, role_id=None, role_action="nessuna",
                cooldown_seconds=60, ping_ruoli=False, uses=0, permesso=None, bersaglio=False, cancella_innesco=False,
                invio="canale", canale_id=None, reazioni=[], si_cancella_dopo=None, cancella_messaggi=None, solo_nsfw=False,
                anche_modificati=False, gruppo=None, created_by=None, pausa_ambito="utente", ruoli_vietati=[],
                canali_vietati=[], utenti_vietati=[], embed_nome=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_utl_012_la_pausa_vale_per_utente_canale_o_server():
    modulo._ultimo_uso.__init__(100)
    per_utente = _tag(pausa_ambito="utente")
    assert CustomCommandsCog._pausa(per_utente, 1, 5, canale_id=9) == 0
    assert CustomCommandsCog._pausa(per_utente, 1, 5, canale_id=9) > 0
    assert CustomCommandsCog._pausa(per_utente, 1, 6, canale_id=9) == 0  # un altro utente non aspetta
    modulo._ultimo_uso.__init__(100)
    per_canale = _tag(pausa_ambito="canale")
    assert CustomCommandsCog._pausa(per_canale, 1, 5, canale_id=9) == 0
    assert CustomCommandsCog._pausa(per_canale, 1, 6, canale_id=9) > 0  # stesso canale, altro utente: aspetta
    assert CustomCommandsCog._pausa(per_canale, 1, 6, canale_id=10) == 0
    modulo._ultimo_uso.__init__(100)
    per_server = _tag(pausa_ambito="server")
    assert CustomCommandsCog._pausa(per_server, 1, 5, canale_id=9) == 0
    assert CustomCommandsCog._pausa(per_server, 1, 6, canale_id=10) > 0


@pytest.mark.asyncio
async def test_utl_038_risposta_nel_canale_scelto_pinga_chi_ha_usato_il_tag():
    """UTL-038: con invio «altro» il messaggio nell'altro canale comincia con la menzione di chi lo ha chiamato."""
    invia = AsyncMock(return_value=None)
    autore = fake_member(5)
    autore.mention = "<@5>"
    await CustomCommandsCog._manda(invia, _tag(invio="altro", canale_id=3), "Ciao a tutti", autore)
    assert invia.await_args.args[0] == "<@5> Ciao a tutti"
    assert invia.await_args.kwargs["allowed_mentions"].users is True and invia.await_args.kwargs["allowed_mentions"].everyone is False
    invia.reset_mock()
    await CustomCommandsCog._manda(invia, _tag(invio="canale"), "Ciao", autore)
    assert invia.await_args.args[0] == "Ciao"


def test_grezzo_non_chiude_il_blocco_e_non_pinga():
    """UTL-007: il testo grezzo sta in un blocco di codice senza uscirne e senza menzioni."""
    t = extra.testo_grezzo("a ```b``` @everyone " + "x" * 3000)
    assert "```" not in t and "@everyone" not in t.replace("@​everyone", "") and len(t) <= 1700


@pytest.fixture
def cog_extra(monkeypatch):
    cog = extra.TagExtraCog(MagicMock())
    r = MagicMock()
    r.get_tag = AsyncMock(return_value=_tag(created_by=7, uses=3, response="Testo <@&5>"))
    r.alias_di = AsyncMock(return_value=["r"])
    monkeypatch.setattr(extra, "custom_command_repo", r)
    d = MagicMock()
    d.is_module_active_for_guild = AsyncMock(return_value=True)
    monkeypatch.setattr(extra, "db", d)
    return cog


@pytest.mark.asyncio
async def test_utl_008_info_mostra_autore_usi_e_alias_e_il_grezzo_solo_se_chiesto(cog_extra):
    """UTL-008: scheda con autore, usi e nomi alternativi; UTL-007: il testo grezzo solo con `grezzo`."""
    i = fake_interaction(guild=fake_guild(), user=fake_member(5))
    await cog_extra.info.callback(cog_extra, i, "regole", False)
    embed = i.response.send_message.await_args.kwargs["embed"]
    assert "<@7>" in embed.description and "3" in embed.description and "`r`" in embed.description
    assert not embed.fields
    assert i.response.send_message.await_args.kwargs["allowed_mentions"].roles is False
    i2 = fake_interaction(guild=fake_guild(), user=fake_member(5))
    await cog_extra.info.callback(cog_extra, i2, "regole", True)
    assert "Testo" in i2.response.send_message.await_args.kwargs["embed"].fields[0].value


@pytest.mark.asyncio
async def test_utl_018_il_tag_manda_l_embed_salvato_con_il_testo(monkeypatch):
    """UTL-018: un tag con `embed_nome` manda l'embed salvato; se l'embed non c'è più risponde solo col testo."""
    salvato = SimpleNamespace(data={"title": "Regole", "description": "Siate gentili"})
    deposito = MagicMock()
    deposito.get = AsyncMock(return_value=salvato)
    monkeypatch.setattr(modulo, "saved_embed_repo", deposito)
    invia = AsyncMock(return_value=None)
    await CustomCommandsCog._manda(invia, _tag(embed_nome="regole"), "Leggi qui")
    assert invia.await_args.args[0] == "Leggi qui" and invia.await_args.kwargs["embed"].title == "Regole"
    deposito.get.return_value = None
    invia.reset_mock()
    await CustomCommandsCog._manda(invia, _tag(embed_nome="regole"), "Leggi qui")
    assert "embed" not in invia.await_args.kwargs


def test_utl_036_i_comandi_di_gestione_dei_tag_sono_solo_per_chi_gestisce_il_server():
    """UTL-036: il gruppo /admin-tag (crea, modifica, elimina, info, alias, divieti) si apre solo con «Gestire il server»."""
    from core.command_groups import _DEFINIZIONI
    descrizione, permesso, _livello = _DEFINIZIONI["admin-tag"]
    assert permesso == "manage_guild"
