"""
tests/test_panel_ticket.py
==========================
Risposta a un ticket dal sito (TKT-085, SPEC §24.9): solo lo staff del ticket, permessi riletti a ogni richiesta,
messaggio nel canale del ticket con le menzioni spente e il nome di chi risponde. Sessioni e database veri, Discord finto.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from core.database import db
from core.repositories.ticket_repo import ticket_repo
from tests.support.discord_fakes import fake_member, fake_role
from tests.test_web_panel_server import ADMIN, GUILD, _client, _csrf, _entra, ambiente  # noqa: F401

BASE = f"/server/{GUILD}/ticket"
CANALE = 5550
RUOLO_STAFF = 4040
UTENTE_TICKET = 700


@pytest.fixture
async def tk(ambiente, clean_db, monkeypatch):  # noqa: F811
    monkeypatch.setattr(ticket_repo, "_pool_provider", lambda: clean_db)
    await db.ensure_guild_exists(GUILD)
    await db.set_guild_setting(GUILD, "ticket_support_role_ids", [RUOLO_STAFF])
    guild = ambiente.bot.guilds[0]
    canale = MagicMock(spec=discord.TextChannel)
    canale.id = CANALE
    canale.guild = guild
    canale.send = AsyncMock()
    canale.permissions_for = MagicMock(return_value=discord.Permissions(send_messages=True))  # senza webhook: risponde il bot
    guild.get_channel_or_thread = MagicMock(side_effect=lambda i: canale if i == CANALE else None)
    ambiente.canale = canale
    # ADMIN: ruolo di supporto, senza «Gestisci server». Il pannello lo ammette col ruolo «scrittura».
    ruolo = fake_role(RUOLO_STAFF, "Supporto")
    ambiente.membri[ADMIN] = fake_member(ADMIN, "Mario <b>", roles=[ruolo], guild_permissions=discord.Permissions(manage_guild=True))
    await ticket_repo.create_ticket(GUILD, UTENTE_TICKET, CANALE, category_label="Aiuto")
    ambiente.ticket = await ticket_repo.get_ticket_by_channel(CANALE)
    return ambiente


@pytest.mark.asyncio
async def test_risposta_nel_canale_senza_menzioni_e_col_nome(tk):
    client = await _client(tk.app)
    try:
        await _entra(client)
        pagina = await (await client.get(BASE)).text()
        assert f"{BASE}/{tk.ticket.id}" in pagina
        form = await (await client.get(f"{BASE}/{tk.ticket.id}")).text()
        assert "maxlength" in form
        csrf = await _csrf(client, f"{BASE}/{tk.ticket.id}")
        assert (await client.post(f"{BASE}/{tk.ticket.id}/rispondi", data={"testo": "ciao"})).status == 403
        tk.canale.send.assert_not_called()
        r = await client.post(
            f"{BASE}/{tk.ticket.id}/rispondi", data={"csrf": csrf, "testo": "Ciao @everyone <@1>"}, allow_redirects=False
        )
        assert r.status == 302 and "esito=ticket_inviato" in r.headers["Location"]
        tk.canale.send.assert_awaited_once()
        args, kw = tk.canale.send.await_args
        testo = kw.get("content") or args[0]
        assert "Mario" in testo and "Ciao" in testo and "sito" in testo
        mentions = kw["allowed_mentions"]
        assert not mentions.everyone and mentions.users is False and mentions.roles is False
        assert (await ticket_repo.get_ticket_by_channel(CANALE)).first_response_at is not None
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_testo_vuoto_o_troppo_lungo_non_parte(tk):
    client = await _client(tk.app)
    try:
        await _entra(client)
        csrf = await _csrf(client, f"{BASE}/{tk.ticket.id}")
        for testo in ("", "   \n ", "x" * 1501):
            r = await client.post(f"{BASE}/{tk.ticket.id}/rispondi", data={"csrf": csrf, "testo": testo}, allow_redirects=False)
            assert "esito=non_valido" in r.headers["Location"]
        tk.canale.send.assert_not_called()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_chi_non_e_staff_del_ticket_non_scrive_e_la_risposta_e_uguale(tk):
    # Gestisce il pannello (ruolo scrittura via manage_guild) ma lo staff del ticket è un altro ruolo e non ha «Gestisci server».
    tk.membri[ADMIN] = fake_member(ADMIN, "Estraneo", roles=[], guild_permissions=discord.Permissions(administrator=True))
    await db.set_guild_setting(GUILD, "ticket_support_role_ids", [999])
    client = await _client(tk.app)
    try:
        await _entra(client)
        niente = await client.get(f"{BASE}/{tk.ticket.id}")
        inesistente = await client.get(f"{BASE}/999999")
        assert niente.status == inesistente.status == 404 or niente.status == inesistente.status == 403
        assert (await niente.text()) == (await inesistente.text())
        r = await client.post(f"{BASE}/{tk.ticket.id}/rispondi", data={"csrf": "x", "testo": "ciao"})
        assert r.status in (403, 404)
        tk.canale.send.assert_not_called()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_ticket_di_un_altro_server_o_chiuso_non_si_risponde(tk, clean_db):
    client = await _client(tk.app)
    try:
        await _entra(client)
        csrf = await _csrf(client, f"{BASE}/{tk.ticket.id}")
        await clean_db.execute("UPDATE tickets SET guild_id = 1 WHERE id = $1", tk.ticket.id)
        r = await client.post(f"{BASE}/{tk.ticket.id}/rispondi", data={"csrf": csrf, "testo": "ciao"})
        assert r.status == 404
        await clean_db.execute("UPDATE tickets SET guild_id = $2, status = 'closed' WHERE id = $1", tk.ticket.id, GUILD)
        r = await client.post(f"{BASE}/{tk.ticket.id}/rispondi", data={"csrf": csrf, "testo": "ciao"})
        assert r.status == 404
        tk.canale.send.assert_not_called()
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_discord_rifiuta_l_invio_niente_dettagli(tk):
    tk.canale.send.side_effect = discord.Forbidden(MagicMock(status=403), "segreto interno")
    client = await _client(tk.app)
    try:
        await _entra(client)
        csrf = await _csrf(client, f"{BASE}/{tk.ticket.id}")
        r = await client.post(f"{BASE}/{tk.ticket.id}/rispondi", data={"csrf": csrf, "testo": "ciao"}, allow_redirects=False)
        assert "esito=ticket_non_inviato" in r.headers["Location"]
        assert "segreto" not in r.headers["Location"]
    finally:
        await client.close()
