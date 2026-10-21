"""
tests/test_ticket_opzioni.py
============================
#120 (catalogo ticket): /ticket opzioni …, lista nera, sospensione, pausa, reperibili,
/ticket apri (anche per conto di un utente e da un messaggio) e l'apertura con le
opzioni del pannello. Database vero; Discord finto.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, create_autospec

import discord
import pytest
from discord import app_commands

import cogs.tickets.opzioni as opz
import cogs.tickets.tickets as modulo
from core.database import db
from core.repositories.ticket_form_repo import ticket_form_repo
from core.repositories.ticket_opzioni_repo import ticket_opzioni_repo
from core.repositories.ticket_repo import ticket_repo
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role, fake_text_channel

ID_SERVER = 100
ID_CATEGORIA = 900
ID_RISERVA = 901
UTENTE = 20
STAFF = 30
RUOLO_VIP = 111111111111111111
RUOLO_OSS = 222222222222222222
RUOLO_SQUADRA = 333333333333333333


@pytest.fixture(autouse=True)
async def _ambiente(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(ID_SERVER, modulo.MODULE_TICKETS, True)
    yield
    database_module.db._modules_cache.clear()


def _categoria(cid, canali=0):
    c = create_autospec(discord.CategoryChannel, instance=True)
    c.id = cid
    c.channels = [object()] * canali
    return c


class Server:
    def __init__(self) -> None:
        self.guild = fake_guild(ID_SERVER)
        self.guild.default_role = fake_role(role_id=ID_SERVER, name="@everyone", position=0)
        self.guild.me = fake_member(999, bot=True)
        self.guild.me.top_role = fake_role(role_id=998, position=50)
        self.ruoli = {r: fake_role(role_id=r, position=5) for r in (RUOLO_VIP, RUOLO_OSS, RUOLO_SQUADRA)}
        self.categoria = _categoria(ID_CATEGORIA)
        self.riserva = _categoria(ID_RISERVA)
        self.canali: list = []
        self.membri: dict[int, MagicMock] = {}
        for c in (self.categoria, self.riserva):
            c.create_text_channel.side_effect = self._crea
        self.guild.get_role = MagicMock(side_effect=self.ruoli.get)
        self.guild.get_channel = MagicMock(
            side_effect=lambda i: {ID_CATEGORIA: self.categoria, ID_RISERVA: self.riserva}.get(i)
        )
        self.guild.get_member = MagicMock(side_effect=self.membri.get)

    async def _crea(self, name, **kwargs):
        canale = fake_text_channel(1000 + len(self.canali), name)
        canale.guild = self.guild
        canale.send = AsyncMock(return_value=MagicMock(pin=AsyncMock(), delete=AsyncMock()))
        self.canali.append((canale, {"name": name, **kwargs}))
        return canale

    def membro(self, uid, *, ruoli=(), admin=False):
        m = fake_member(uid, roles=[self.ruoli.get(r) or fake_role(role_id=r) for r in ruoli],
                        guild_permissions=discord.Permissions(manage_guild=admin, administrator=admin))
        m.guild = self.guild
        m.send = AsyncMock()
        m.add_roles = AsyncMock()
        self.membri[uid] = m
        return m

    def inter(self, user, canale=None):
        return fake_interaction(guild=self.guild, user=user, channel=canale or fake_text_channel(5))


async def _pannello(nome="Supporto"):
    return await ticket_form_repo.crea_pannello(ID_SERVER, nome, ID_CATEGORIA, "Apri")


def _cog():
    return opz.TicketOpzioniCog(bot=None)


def _risposta(inter) -> str:
    return str(inter.response.send_message.call_args)


# ---------------------------------------------------------------- opzioni
async def test_limiti_si_salvano_e_un_ruolo_inesistente_viene_rifiutato():
    s = Server()
    p = await _pannello()
    admin = s.membro(STAFF, admin=True)
    inter = s.inter(admin)
    await _cog().limiti.callback(_cog(), inter, "Supporto", 3, 30, f"<@&{RUOLO_VIP}>")
    o = await ticket_opzioni_repo.opzioni(p.id)
    assert (o.max_aperti, o.pausa_secondi, o.ruoli_esenti) == (3, 1800, (RUOLO_VIP,))
    inter = s.inter(admin)
    await _cog().limiti.callback(_cog(), inter, "Supporto", 0, None, "444444444444444444")
    assert "non esiste" in _risposta(inter)
    assert (await ticket_opzioni_repo.opzioni(p.id)).max_aperti == 3


async def test_orari_sbagliati_non_si_salvano():
    s = Server()
    p = await _pannello()
    inter = s.inter(s.membro(STAFF, admin=True))
    await _cog().orari.callback(_cog(), inter, "Supporto", "lun-xyz 9:00-18:00", None, None, None)
    assert "Giorno sconosciuto" in _risposta(inter)
    await _cog().orari.callback(_cog(), s.inter(s.membro(STAFF, admin=True)), "Supporto",
                                "lun-ven 09:00-18:00", "Europe/Rome", "Torniamo alle 9.", True)
    o = await ticket_opzioni_repo.opzioni(p.id)
    assert o.orari == "lun-ven 09:00-18:00" and o.fuori_orario_apri and o.fuori_orario_testo == "Torniamo alle 9."


async def test_regole_di_accesso_in_ordine():
    s = Server()
    p = await _pannello()
    admin = s.membro(STAFF, admin=True)
    for ruolo, regola in ((RUOLO_VIP, "nega"), (RUOLO_OSS, "permetti"), (RUOLO_VIP, "permetti")):
        await _cog().accesso.callback(_cog(), s.inter(admin), "Supporto", s.ruoli[ruolo],
                                      app_commands.Choice(name=regola, value=regola))
    assert (await ticket_opzioni_repo.situazione(ID_SERVER, 1, [], p.id)).regole_accesso == [(RUOLO_VIP, True), (RUOLO_OSS, True)]
    await _cog().accesso.callback(_cog(), s.inter(admin), "Supporto", s.ruoli[RUOLO_VIP],
                                  app_commands.Choice(name="togli", value="togli"))
    assert (await ticket_opzioni_repo.situazione(ID_SERVER, 1, [], p.id)).regole_accesso == [(RUOLO_OSS, True)]


async def test_mostra_le_opzioni_in_un_embed():
    s = Server()
    await _pannello()
    inter = s.inter(s.membro(STAFF, admin=True))
    await _cog().mostra.callback(_cog(), inter, "Supporto")
    embed = inter.response.send_message.call_args.kwargs["embed"]
    assert len(embed) < 6000 and len(embed.fields) == 8


# ---------------------------------------------------------------- regole del server
async def test_lista_nera_blocca_l_apertura_ma_non_lo_staff():
    s = Server()
    admin = s.membro(STAFF, admin=True)
    utente = s.membro(UTENTE)
    await _cog().lista_nera.callback(_cog(), s.inter(admin), app_commands.Choice(name="aggiungi", value="aggiungi"),
                                     utente, None, "spam")
    esito = await modulo.esito_apertura(s.guild, utente, None)
    assert not esito.permesso and "Non puoi aprire" in esito.messaggio
    assert (await modulo.esito_apertura(s.guild, admin, None)).permesso
    await _cog().lista_nera.callback(_cog(), s.inter(admin), app_commands.Choice(name="togli", value="togli"),
                                     utente, None, None)
    assert (await modulo.esito_apertura(s.guild, utente, None)).permesso


async def test_sospensione_con_motivo_e_ripresa():
    s = Server()
    admin = s.membro(STAFF, admin=True)
    utente = s.membro(UTENTE)
    await _cog().sospendi.callback(_cog(), s.inter(admin), "Manutenzione", 2)
    esito = await modulo.esito_apertura(s.guild, utente, None)
    assert not esito.permesso and "Manutenzione" in esito.messaggio
    await _cog().sospendi.callback(_cog(), s.inter(admin), None, None)
    assert (await modulo.esito_apertura(s.guild, utente, None)).permesso


async def test_la_pausa_si_azzera_dallo_staff():
    s = Server()
    p = await _pannello()
    await ticket_opzioni_repo.imposta(p.id, pausa_secondi=3600)
    utente = s.membro(UTENTE)
    await ticket_repo.create_ticket(ID_SERVER, UTENTE, 50, ticket_number=1, panel_id=p.id)
    await ticket_repo.close_ticket(50, STAFF)
    assert "riprova tra" in (await modulo.esito_apertura(s.guild, utente, p.id)).messaggio
    inter = s.inter(utente)
    await _cog().azzera_pausa.callback(_cog(), inter, utente)
    assert "Solo lo staff" in _risposta(inter)
    await _cog().azzera_pausa.callback(_cog(), s.inter(s.membro(STAFF, admin=True)), utente)
    assert (await modulo.esito_apertura(s.guild, utente, p.id)).permesso


async def test_reperibile_si_accende_e_si_spegne_solo_per_lo_staff():
    s = Server()
    inter = s.inter(s.membro(UTENTE))
    await _cog().reperibile.callback(_cog(), inter)
    assert "Solo lo staff" in _risposta(inter)
    staff = s.membro(STAFF, admin=True)
    await _cog().reperibile.callback(_cog(), s.inter(staff))
    assert await ticket_opzioni_repo.reperibili(ID_SERVER) == [STAFF]
    await _cog().reperibile.callback(_cog(), s.inter(staff))
    assert await ticket_opzioni_repo.reperibili(ID_SERVER) == []


# ---------------------------------------------------------------- apertura con le opzioni
async def test_l_apertura_usa_nome_permessi_osservatori_squadra_reperibili_e_ruoli_durante():
    s = Server()
    p = await _pannello()
    await ticket_opzioni_repo.imposta(
        p.id, nome_modello="aiuto-{utente}-{num}", permessi_negati=("allegati",),
        ruoli_osservatori=(RUOLO_OSS,), ruoli_staff=(RUOLO_SQUADRA,), ruoli_durante=(RUOLO_VIP,),
        ping_ruoli=(RUOLO_SQUADRA,), ping_cancella=True, fissa_primo=True, dm_apertura="Ciao {utente}!",
    )
    reperibile = s.membro(STAFF + 1, admin=True)
    await ticket_opzioni_repo.cambia_reperibile(ID_SERVER, reperibile.id)
    utente = s.membro(UTENTE)
    panel = await ticket_form_repo.pannello_per_id(p.id)
    await modulo._open_ticket_channel(s.inter(utente), s.guild, s.categoria, panel.name, panel=panel)

    canale, kwargs = s.canali[-1]
    assert kwargs["name"] == "aiuto-utente-1"
    ow = kwargs["overwrites"]
    assert ow[utente].attach_files is False and ow[utente].send_messages is True
    assert ow[s.ruoli[RUOLO_OSS]].view_channel is True and ow[s.ruoli[RUOLO_OSS]].send_messages is False
    assert ow[s.ruoli[RUOLO_SQUADRA]].send_messages is True
    assert ow[reperibile].view_channel is True
    utente.add_roles.assert_awaited_once()
    t = await ticket_repo.get_ticket_by_channel(canale.id)
    assert t.ruoli_dati == (RUOLO_VIP,)
    utente.send.assert_awaited_once()
    assert "Ciao" in utente.send.call_args.args[0]


async def test_categoria_piena_passa_alla_riserva():
    s = Server()
    s.categoria.channels = [object()] * 50
    p = await _pannello()
    await ticket_opzioni_repo.imposta(p.id, categorie_riserva=(ID_RISERVA,))
    panel = await ticket_form_repo.pannello_per_id(p.id)
    await modulo._open_ticket_channel(s.inter(s.membro(UTENTE)), s.guild, s.categoria, panel.name, panel=panel)
    s.riserva.create_text_channel.assert_awaited_once()
    s.categoria.create_text_channel.assert_not_awaited()


async def test_fuori_orario_con_apertura_lo_stesso_mette_l_avviso():
    s = Server()
    p = await _pannello()
    # Nessuna fascia contiene l'istante attuale: un giorno solo, un minuto solo, ieri.
    ieri = (datetime.now(timezone.utc) - timedelta(days=1)).astimezone()
    giorno = ("lun", "mar", "mer", "gio", "ven", "sab", "dom")[ieri.weekday()]
    await ticket_opzioni_repo.imposta(p.id, orari=f"{giorno} 00:00-00:01", fuso="UTC", fuori_orario_apri=True)
    panel = await ticket_form_repo.pannello_per_id(p.id)
    await modulo._open_ticket_channel(s.inter(s.membro(UTENTE)), s.guild, s.categoria, panel.name, panel=panel)
    canale, _ = s.canali[-1]
    embed = canale.send.await_args_list[0].kwargs["embed"]
    assert any(f.name == "Fuori orario" for f in embed.fields)


# ---------------------------------------------------------------- /ticket apri
async def test_apri_per_conto_di_un_utente_solo_per_lo_staff():
    s = Server()
    utente = s.membro(UTENTE)
    altro = s.membro(UTENTE + 1)
    await db.set_guild_setting(ID_SERVER, modulo.SETTING_CATEGORY, ID_CATEGORIA)
    inter = s.inter(altro)
    await _cog().apri.callback(_cog(), inter, None, "aiuto", utente, None, False)
    assert "Solo lo staff" in _risposta(inter)
    assert s.canali == []

    staff = s.membro(STAFF, admin=True)
    await _cog().apri.callback(_cog(), s.inter(staff), None, "Problema col pagamento", utente, None, False)
    canale, kwargs = s.canali[-1]
    assert utente in kwargs["overwrites"]
    t = await ticket_repo.get_ticket_by_channel(canale.id)
    assert t.user_id == UTENTE
    embed = canale.send.await_args_list[0].kwargs["embed"]
    assert {"Aperto dallo staff", "Motivo"} <= {f.name for f in embed.fields}


async def test_apri_da_un_messaggio_lo_cita_e_aggiunge_l_autore():
    s = Server()
    await db.set_guild_setting(ID_SERVER, modulo.SETTING_CATEGORY, ID_CATEGORIA)
    autore = s.membro(UTENTE + 5)
    origine = fake_text_channel(777)
    origine.permissions_for = MagicMock(return_value=discord.Permissions(view_channel=True, read_message_history=True))
    citato = MagicMock(content="messaggio offensivo", author=autore,
                       jump_url="https://discord.com/channels/100/777/888")
    origine.fetch_message = AsyncMock(return_value=citato)
    s.guild.get_channel_or_thread = MagicMock(return_value=origine)
    staff = s.membro(STAFF, admin=True)
    link = f"https://discord.com/channels/{ID_SERVER}/777/888"
    await _cog().apri.callback(_cog(), s.inter(staff), None, None, None, link, True)
    canale, _ = s.canali[-1]
    embed = canale.send.await_args_list[0].kwargs["embed"]
    assert any("messaggio offensivo" in f.value for f in embed.fields)
    canale.set_permissions.assert_awaited_once()
    assert canale.set_permissions.call_args.args[0] is autore


async def test_apri_con_un_link_di_un_altro_server_non_apre():
    s = Server()
    await db.set_guild_setting(ID_SERVER, modulo.SETTING_CATEGORY, ID_CATEGORIA)
    inter = s.inter(s.membro(UTENTE))
    link = "https://discord.com/channels/999999999999999999/777777777777777777/888888888888888888"
    await _cog().apri.callback(_cog(), inter, None, None, None, link, False)
    assert "non è di un messaggio di questo server" in str(inter.followup.send.call_args)
    assert s.canali == []


async def test_apri_per_conto_con_un_messaggio_che_l_utente_non_vede_non_apre():
    """Fuga di contenuto: lo staff cita un messaggio di un canale dello staff nel ticket di un utente."""
    s = Server()
    await db.set_guild_setting(ID_SERVER, modulo.SETTING_CATEGORY, ID_CATEGORIA)
    utente = s.membro(UTENTE)
    staff = s.membro(STAFF, admin=True)
    origine = fake_text_channel(777)
    origine.permissions_for = MagicMock(
        side_effect=lambda m: discord.Permissions(view_channel=True, read_message_history=True)
        if m is staff else discord.Permissions.none()
    )
    origine.fetch_message = AsyncMock(return_value=MagicMock(content="segreto dello staff", author=staff))
    s.guild.get_channel_or_thread = MagicMock(return_value=origine)
    inter = s.inter(staff)
    link = f"https://discord.com/channels/{ID_SERVER}/777/888"
    await _cog().apri.callback(_cog(), inter, None, None, utente, link, False)
    assert s.canali == []
    assert "non puoi leggerlo" in str(inter.followup.send.call_args)


async def test_apri_con_un_messaggio_di_un_thread_privato_di_cui_non_si_e_membri_non_apre():
    """I thread privati (come le note dello staff) non hanno permessi propri: conta l'essere membri."""
    s = Server()
    await db.set_guild_setting(ID_SERVER, modulo.SETTING_CATEGORY, ID_CATEGORIA)
    utente = s.membro(UTENTE)
    thread = create_autospec(discord.Thread, instance=True)
    thread.id = 777
    thread.type = discord.ChannelType.private_thread
    thread.permissions_for = MagicMock(
        return_value=discord.Permissions(view_channel=True, read_message_history=True)
    )
    risposta = MagicMock(status=404, reason="Not Found")
    thread.fetch_member = AsyncMock(side_effect=discord.NotFound(risposta, "Unknown Member"))
    thread.fetch_message = AsyncMock(return_value=MagicMock(content="nota dello staff", author=s.membro(STAFF)))
    s.guild.get_channel_or_thread = MagicMock(return_value=thread)
    inter = s.inter(utente)
    link = f"https://discord.com/channels/{ID_SERVER}/777/888"
    await _cog().apri.callback(_cog(), inter, None, None, None, link, False)
    assert s.canali == []
    thread.fetch_message.assert_not_awaited()


async def test_ruoli_durante_non_accetta_ruoli_sopra_chi_configura_ne_ruoli_pericolosi():
    """Chi apre un ticket li prende da solo: un admin non deve poter dare a tutti un ruolo sopra il suo, o forte."""
    s = Server()
    p = await _pannello()
    forte = 444444444444444444
    s.ruoli[forte] = fake_role(role_id=forte, position=1, permissions=discord.Permissions(ban_members=True))
    admin = s.membro(STAFF, admin=True)
    admin.top_role = fake_role(role_id=555, position=3)
    for ruolo in (RUOLO_VIP, forte):  # VIP sta a 5, sopra l'admin; "forte" ha ban_members
        inter = s.inter(admin)
        await _cog().permessi.callback(_cog(), inter, p.name, None, None, str(ruolo), None)
        assert "Opzioni salvate" not in _risposta(inter), ruolo
    assert (await ticket_opzioni_repo.opzioni(p.id)).ruoli_durante == ()


async def test_ruolo_durante_diventato_pericoloso_non_si_da_all_apertura():
    s = Server()
    p = await _pannello()
    await ticket_opzioni_repo.imposta(p.id, ruoli_durante=(RUOLO_VIP,))
    s.ruoli[RUOLO_VIP].permissions = discord.Permissions(administrator=True)
    utente = s.membro(UTENTE)
    panel = await ticket_form_repo.pannello_per_id(p.id)
    await modulo._open_ticket_channel(s.inter(utente), s.guild, s.categoria, panel.name, panel=panel)
    utente.add_roles.assert_not_awaited()


async def test_tetto_del_pannello_tiene_con_due_utenti_insieme(clean_db):
    """Il tetto si legge in esito_apertura: due persone insieme passavano entrambe il controllo."""
    import asyncio

    from tests.support.concorrenza import apri_connessioni

    s = Server()
    p = await _pannello()
    await ticket_opzioni_repo.imposta(p.id, max_aperti=1)
    panel = await ticket_form_repo.pannello_per_id(p.id)
    a, b = s.membro(UTENTE), s.membro(UTENTE + 1)
    await apri_connessioni(clean_db, 4)
    await asyncio.gather(*(
        modulo._open_ticket_channel(s.inter(m), s.guild, s.categoria, panel.name, panel=panel) for m in (a, b)
    ))
    aperti = await clean_db.fetchval("SELECT count(*) FROM tickets WHERE panel_id = $1 AND status = 'open'", p.id)
    assert aperti == 1


async def test_cache_delle_opzioni_si_svuota_a_ogni_modifica_e_risparmia_le_query(monkeypatch):
    p = await _pannello()
    assert (await ticket_opzioni_repo.opzioni(p.id)).max_aperti is None  # ora in cache
    await ticket_opzioni_repo.imposta(p.id, max_aperti=3)
    assert (await ticket_opzioni_repo.opzioni(p.id)).max_aperti == 3
    await ticket_opzioni_repo.imposta_regola(p.id, 555, False)
    s = await ticket_opzioni_repo.situazione(ID_SERVER, UTENTE, [], p.id)
    assert s.regole_accesso == [(555, False)] and s.opzioni.max_aperti == 3

    # Dentro la cache: nessuna lettura delle opzioni per il secondo clic.
    letture = []
    pool = db.pool

    class Contatore:
        async def fetchrow(self, query, *args):
            letture.append(query)
            return await pool.fetchrow(query, *args)

    monkeypatch.setattr(ticket_opzioni_repo, "_pool_provider", Contatore)
    await ticket_opzioni_repo.situazione(ID_SERVER, UTENTE, [], p.id)
    assert len(letture) == 2 and not any("ticket_panel_opzioni" in q for q in letture)
