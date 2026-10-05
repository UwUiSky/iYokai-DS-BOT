"""
tests/test_logs_query_limiti.py
===============================
/logs user e /logs channel restano dentro i 4096 caratteri di una
descrizione (LIM-15); /logs export divide lo storico in più file,
ognuno sotto il limite di peso (LIM-55), e ogni file è un JSON valido.

Database vero (clean_db): gli eventi li scrive il repository usato in
produzione dai listener dei log.
"""

import json
from unittest.mock import MagicMock

import discord
import pytest

import cogs.logging.logs_query as modulo
from core.repositories.event_log_repo import event_log_repo
from tests.support.discord_fakes import fake_interaction, fake_member, fake_text_channel

ID_SERVER = 100
ID_UTENTE = 20
ID_CANALE = 30
DIECI_MIB = 10 * 1024 * 1024


@pytest.fixture(autouse=True)
def _ambiente(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)


def _interazione():
    interazione = fake_interaction()
    interazione.guild.id = ID_SERVER
    return interazione


async def _scrivi_eventi(quanti: int, caratteri: int) -> None:
    for numero in range(quanti):
        await event_log_repo.log_event(
            ID_SERVER,
            "nickname_update",
            actor_id=1,
            target_user_id=ID_UTENTE,
            channel_id=ID_CANALE,
            details={"numero": numero, "before": "p" * caratteri, "after": "d" * caratteri},
        )


async def test_logs_user_25_voci_lunghe_un_embed_valido():
    await _scrivi_eventi(25, 500)
    cog = modulo.LogsQueryCog(bot=None)
    interazione = _interazione()

    await cog.logs_user.callback(cog, interazione, fake_member(ID_UTENTE), 25)

    embed = interazione.response.send_message.call_args.kwargs["embed"]
    assert len(embed.description) <= 4096
    assert len(embed) <= 6000
    # Ogni voce è tagliata, quindi entrano tutte e 25.
    assert embed.description.count("**nickname_update**") == 25


async def test_logs_channel_25_voci_lunghe_un_embed_valido():
    await _scrivi_eventi(25, 500)
    cog = modulo.LogsQueryCog(bot=None)
    interazione = _interazione()

    await cog.logs_channel.callback(cog, interazione, fake_text_channel(ID_CANALE), 25)

    embed = interazione.response.send_message.call_args.kwargs["embed"]
    assert len(embed.description) <= 4096
    assert embed.description.count("**nickname_update**") == 25


def test_voce_con_accento_grave_nei_dettagli_non_rompe_il_blocco():
    """Un nickname con ` chiuderebbe il blocco di codice a metà."""
    from core.repositories.event_log_repo import EventLogEntry

    voce = EventLogEntry(
        id=1,
        guild_id=ID_SERVER,
        event_type="nickname_update",
        actor_id=None,
        target_user_id=ID_UTENTE,
        channel_id=None,
        role_id=None,
        case_number=None,
        details={"after": "a`b"},
        created_at=discord.utils.utcnow(),
    )

    assert modulo._format_entry(voce).count("`") == 4  # `#1` e `{…}`


def test_dividi_export_ogni_parte_sotto_il_limite_ed_e_json_valido():
    eventi = [{"id": n, "details": {"testo": "x" * 100}} for n in range(200)]

    parti = modulo.split_export(eventi, max_bytes=2000)

    assert len(parti) > 1
    ricostruiti = []
    for parte in parti:
        assert len(parte) <= 2000
        ricostruiti.extend(json.loads(parte.decode("utf-8")))
    assert ricostruiti == eventi


def test_dividi_export_senza_eventi_un_file_con_lista_vuota():
    assert [json.loads(p) for p in modulo.split_export([], max_bytes=2000)] == [[]]


def test_il_limite_di_peso_resta_sotto_dieci_mib():
    assert modulo.MAX_EXPORT_FILE_BYTES < DIECI_MIB


async def test_export_grande_arriva_in_piu_file_tutti_sotto_il_limite(monkeypatch):
    monkeypatch.setattr(modulo, "MAX_EXPORT_FILE_BYTES", 3000)
    await _scrivi_eventi(30, 200)
    cog = modulo.LogsQueryCog(bot=None)
    interazione = _interazione()

    await cog.logs_export.callback(cog, interazione)

    interazione.response.defer.assert_awaited_once()
    invii = interazione.followup.send.call_args_list
    assert len(invii) > 1
    totale = []
    for invio in invii:
        file = invio.kwargs["file"]
        contenuto = file.fp.read()
        assert len(contenuto) <= 3000
        totale.extend(json.loads(contenuto.decode("utf-8")))
        assert invio.kwargs["ephemeral"] is True
    assert [e["details"]["numero"] for e in totale] == list(range(30))
    assert "30 eventi" in invii[0].args[0]


async def test_export_file_rifiutato_da_discord_risposta_chiara():
    await _scrivi_eventi(2, 10)
    cog = modulo.LogsQueryCog(bot=None)
    interazione = _interazione()
    risposte = []

    async def _invia(*args, **kwargs):
        if "file" in kwargs:
            raise discord.HTTPException(
                MagicMock(status=413, reason="Payload Too Large"), "Request entity too large"
            )
        risposte.append(args[0])

    interazione.followup.send.side_effect = _invia

    await cog.logs_export.callback(cog, interazione)

    assert len(risposte) == 1
    assert "Non sono riuscito" in risposte[0]
