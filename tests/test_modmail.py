"""
tests/test_modmail.py
=====================
NF-33 (#104): ticket via messaggio privato (ModMail).
Regole pure, repository veri (clean_db) e il codice di produzione del cog;
di Discord ci sono solo i finti di tests/support/discord_fakes.py.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, create_autospec

import discord
import pytest

import cogs.tickets.modmail as modulo
from core import channel_router as router
from core import modmail_logic as logica
from core.database import db
from core.repositories.modmail_repo import ConversazioneGiaAperta, modmail_repo
from core.scheduler import Scheduler
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_member,
    fake_message,
    fake_role,
    fake_text_channel,
)
from tests.support.percorsi import percorsi_del_gruppo

ID_SERVER = 100
ID_ALTRO_SERVER = 101
ID_UTENTE = 20
ID_STAFF = 30
ID_CATEGORIA = 900
ID_RUOLO = 500


# ====================================================================
# Regole pure
# ====================================================================
def test_decisione_del_server():
    assert logica.decidi_server([]).esito is logica.Esito.NESSUN_SERVER
    assert logica.decidi_server([5, 5]).esito is logica.Esito.UN_SERVER
    d = logica.decidi_server(list(range(40)))
    assert d.esito is logica.Esito.SCEGLI_SERVER and len(d.guild_ids) == 25  # limite del menu


def test_nome_del_canale_sempre_valido():
    assert logica.nome_canale("Mario Rossi!", 1) == "modmail-mario-rossi"
    assert logica.nome_canale("Ünï", 7) == "modmail-uni"
    assert logica.nome_canale("日本語", 77) == "modmail-77"
    assert len(logica.nome_canale("a" * 300, 1)) <= 100


def test_allegati_e_testo_entro_i_limiti():
    allegati = [(f"file{i}.png", "https://cdn.example/" + "x" * 80) for i in range(30)]
    assert len(logica.elenco_allegati(allegati)) <= 1024
    assert len(logica.testo_inoltrato("a" * 9000)) <= 4096


def test_firma_anonima_non_contiene_il_nome_dello_staff():
    assert "Mario" not in logica.etichetta_firma(True, "Mario", "Il Server")
    assert "Mario" in logica.etichetta_firma(False, "Mario", "Il Server")


def test_limitatore_cinque_messaggi_ogni_dieci_secondi():
    lim = logica.LimitatoreDM()
    assert [lim.consenti(1, t) for t in (0, 1, 2, 3, 4, 5)] == [True] * 5 + [False]
    assert lim.consenti(1, 10.5)  # la finestra scorre
    assert lim.consenti(2, 5)  # un altro utente non è toccato


# ====================================================================
# Repository
# ====================================================================
@pytest.fixture(autouse=True)
async def _ambiente(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(ID_SERVER, "tickets", True)
    await db.set_module_active_for_guild(ID_ALTRO_SERVER, "tickets", True)
    yield
    database_module.db._modules_cache.clear()


async def test_una_sola_conversazione_aperta_per_utente_in_tutti_i_server():
    await modmail_repo.crea(ID_SERVER, ID_UTENTE, 1)
    with pytest.raises(ConversazioneGiaAperta):
        await modmail_repo.crea(ID_ALTRO_SERVER, ID_UTENTE, 2)
    assert await modmail_repo.chiudi(1, ID_STAFF, "fatto")
    await modmail_repo.crea(ID_ALTRO_SERVER, ID_UTENTE, 2)  # chiusa la prima, si può riaprire


async def test_blocco_per_server():
    await modmail_repo.blocca(ID_SERVER, ID_UTENTE, ID_STAFF)
    assert await modmail_repo.bloccato(ID_SERVER, ID_UTENTE)
    assert not await modmail_repo.bloccato(ID_ALTRO_SERVER, ID_UTENTE)
    assert await modmail_repo.sblocca(ID_SERVER, ID_UTENTE)
    assert not await modmail_repo.sblocca(ID_SERVER, ID_UTENTE)


# ====================================================================
# Scena: un server con categoria, un utente, lo staff
# ====================================================================
class Scena:
    def __init__(self, monkeypatch) -> None:
        self.guild = self._server(ID_SERVER, "Server uno")
        self.categoria = create_autospec(discord.CategoryChannel, instance=True)
        self.categoria.id = ID_CATEGORIA
        self.canali: list = []
        self.categoria.create_text_channel.side_effect = self._crea
        self.guild.get_channel.side_effect = self._trova
        self.guild.get_role = MagicMock(
            side_effect=lambda rid: fake_role(role_id=ID_RUOLO) if rid == ID_RUOLO else None
        )
        self.utente = self._utente()
        self.guild.get_member.side_effect = lambda uid: self.utente if uid == ID_UTENTE else None
        self.bot = MagicMock()
        self.bot.guilds = [self.guild]
        self.bot.fetch_user = AsyncMock(return_value=self.utente)
        self.bot.get_channel = lambda cid: next((c for c in self.canali if c.id == cid), None)
        self.scheduler = Scheduler()
        monkeypatch.setattr(modulo, "scheduler", self.scheduler)
        self.log = fake_text_channel(777, "log")
        monkeypatch.setattr(router, "destinazione", AsyncMock(return_value=self.log))
        self.cog = modulo.ModMailCog(self.bot)

    @staticmethod
    def _server(gid, nome):
        g = fake_guild(gid, nome)
        g.default_role = fake_role(role_id=gid, name="@everyone", position=0)
        return g

    def _utente(self):
        u = fake_member(ID_UTENTE, "Mario Rossi")
        u.send = AsyncMock()
        u.created_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        u.joined_at = datetime(2021, 1, 1, tzinfo=timezone.utc)
        u.display_avatar = SimpleNamespace(url="https://cdn.example/a.png")
        u.display_name = "Mario Rossi"
        u.__str__ = lambda self_: "Mario Rossi"
        return u

    def _trova(self, cid):
        if cid == ID_CATEGORIA:
            return self.categoria
        return next((c for c in self.canali if c.id == cid), None)

    async def _crea(self, name, **kwargs):
        c = fake_text_channel(2000 + len(self.canali), name)
        c.guild = self.guild
        c.created_kwargs = kwargs
        self.canali.append(c)
        return c

    async def configura(self):
        await modmail_repo.imposta_categoria(ID_SERVER, ID_CATEGORIA)
        await db.set_guild_setting(ID_SERVER, "ticket_support_role_ids", [ID_RUOLO])

    def dm(self, testo="Ciao, ho un problema", allegati=()):
        m = fake_message(author=self.utente, channel=fake_text_channel(55, "dm"), content=testo)
        m.guild = None
        m.attachments = list(allegati)
        m.add_reaction = AsyncMock()
        return m

    def staff(self, canale, *, manage_guild=True):
        s = fake_member(ID_STAFF, "Staff", guild_permissions=discord.Permissions(manage_guild=manage_guild))
        s.display_name = "Giulia"
        s.guild = self.guild
        i = fake_interaction(guild=self.guild, user=s, channel=canale)
        return i


@pytest.fixture
def scena(monkeypatch):
    return Scena(monkeypatch)


async def test_il_dm_apre_un_canale_privato_per_lo_staff_e_inoltra_il_messaggio(scena):
    await scena.configura()
    m = scena.dm()
    await scena.cog.on_message(m)

    assert len(scena.canali) == 1
    canale = scena.canali[0]
    assert canale.name == "modmail-mario-rossi"
    sovr = canale.created_kwargs["overwrites"]
    assert sovr[scena.guild.default_role].view_channel is False
    assert any(getattr(r, "id", None) == ID_RUOLO for r in sovr)
    thread = await modmail_repo.aperta_dell_utente(ID_UTENTE)
    assert thread.channel_id == canale.id and thread.guild_id == ID_SERVER
    # ultimo messaggio nel canale = quello dell'utente, senza menzioni attive
    ultimo = canale.send.await_args_list[-1]
    assert ultimo.kwargs["embed"].description == "Ciao, ho un problema"
    assert ultimo.kwargs["allowed_mentions"].everyone is False
    m.add_reaction.assert_awaited_once_with("✅")
    assert "Messaggio ricevuto" in m.channel.send.await_args.args[0]


async def test_il_secondo_dm_va_nello_stesso_canale(scena):
    await scena.configura()
    await scena.cog.on_message(scena.dm("uno"))
    await scena.cog.on_message(scena.dm("due"))
    assert len(scena.canali) == 1
    assert scena.canali[0].send.await_args.kwargs["embed"].description == "due"


async def test_allegati_inoltrati_come_link(scena):
    await scena.configura()
    allegato = SimpleNamespace(filename="prova.png", url="https://cdn.example/prova.png")
    await scena.cog.on_message(scena.dm("", [allegato]))
    embed = scena.canali[0].send.await_args.kwargs["embed"]
    assert "prova.png" in embed.fields[0].value


@pytest.mark.parametrize("caso", ["spento", "non_membro", "bloccato", "modulo_spento", "vuoto"])
async def test_nessuna_conversazione_se_non_ci_sono_le_condizioni(scena, caso):
    await scena.configura()
    m = scena.dm()
    if caso == "spento":
        await modmail_repo.imposta_categoria(ID_SERVER, None)
    elif caso == "non_membro":
        scena.guild.get_member.side_effect = lambda uid: None
    elif caso == "bloccato":
        await modmail_repo.blocca(ID_SERVER, ID_UTENTE, ID_STAFF)
    elif caso == "modulo_spento":
        await db.set_module_active_for_guild(ID_SERVER, "tickets", False)
    elif caso == "vuoto":
        m = scena.dm("   ")
    await scena.cog.on_message(m)
    assert scena.canali == []
    assert await modmail_repo.aperta_dell_utente(ID_UTENTE) is None


async def test_i_bot_e_i_messaggi_nei_server_non_aprono_nulla(scena):
    await scena.configura()
    m = scena.dm()
    m.author.bot = True
    await scena.cog.on_message(m)
    m2 = scena.dm()
    m2.guild = scena.guild
    await scena.cog.on_message(m2)
    assert scena.canali == []


async def test_con_due_server_si_chiede_quale_e_si_apre_dopo_la_scelta(scena):
    await scena.configura()
    altro = Scena._server(ID_ALTRO_SERVER, "Server due")
    altro.get_member.side_effect = lambda uid: scena.utente
    altro.get_channel.side_effect = scena.guild.get_channel.side_effect
    await modmail_repo.imposta_categoria(ID_ALTRO_SERVER, ID_CATEGORIA)
    scena.bot.guilds = [scena.guild, altro]

    m = scena.dm()
    await scena.cog.on_message(m)
    assert scena.canali == []
    vista = m.channel.send.await_args.kwargs["view"]
    assert isinstance(vista, modulo.SceltaServerView)
    assert [o.label for o in vista.children[0].options] == ["Server uno", "Server due"]

    interazione = fake_interaction(user=scena.utente)
    interazione.data = {"values": [str(ID_SERVER)]}
    await vista._scelto(interazione)
    assert len(scena.canali) == 1
    assert (await modmail_repo.aperta_dell_utente(ID_UTENTE)).guild_id == ID_SERVER


async def test_sei_dm_di_fila_ne_passano_cinque(scena):
    await scena.configura()
    for n in range(6):
        await scena.cog.on_message(scena.dm(f"m{n}"))
    canale = scena.canali[0]
    testi = [c.kwargs["embed"].description for c in canale.send.await_args_list if c.kwargs["embed"].description]
    assert [t for t in testi if t.startswith("m")] == [f"m{n}" for n in range(5)]


# ---------------------------------------------------------------- risposta dello staff
async def _con_conversazione(scena):
    await scena.configura()
    await scena.cog.on_message(scena.dm())
    return scena.canali[0]


async def test_risposta_anonima_non_mostra_il_nome_dello_staff(scena):
    canale = await _con_conversazione(scena)
    scena.utente.send.reset_mock()
    i = scena.staff(canale)
    await scena.cog.rispondi.callback(scena.cog, i, "Ti rispondiamo noi", True)
    embed = scena.utente.send.await_args.kwargs["embed"]
    assert embed.author.name == "Staff di Server uno"
    assert "Giulia" not in str(embed.to_dict())
    i.response.send_message.assert_awaited_once()  # l'eco per lo staff


async def test_risposta_con_nome(scena):
    canale = await _con_conversazione(scena)
    await scena.cog.rispondi.callback(scena.cog, scena.staff(canale), "ok", False)
    assert "Giulia" in scena.utente.send.await_args.kwargs["embed"].author.name


async def test_rispondi_solo_staff_e_solo_nel_canale_modmail(scena):
    canale = await _con_conversazione(scena)
    scena.utente.send.reset_mock()
    non_staff = scena.staff(canale, manage_guild=False)
    await scena.cog.rispondi.callback(scena.cog, non_staff, "x", False)
    altro_canale = scena.staff(fake_text_channel(9999, "generale"))
    await scena.cog.rispondi.callback(scena.cog, altro_canale, "x", False)
    scena.utente.send.assert_not_awaited()
    assert "Solo lo staff" in non_staff.response.send_message.await_args.args[0]
    assert "ModMail" in altro_canale.response.send_message.await_args.args[0]


async def test_utente_con_dm_chiusi_errore_chiaro(scena):
    canale = await _con_conversazione(scena)
    scena.utente.send.side_effect = discord.Forbidden(SimpleNamespace(status=403, reason="x"), "x")
    i = scena.staff(canale)
    await scena.cog.rispondi.callback(scena.cog, i, "ciao", False)
    assert "messaggi privati chiusi" in i.response.send_message.await_args.args[0]


# ---------------------------------------------------------------- chiusura
async def test_dm_chiudi_chiude_avvisa_l_utente_e_manda_il_transcript_solo_al_log(scena, clean_db):
    canale = await _con_conversazione(scena)
    canale.history = _storia([("nota interna dello staff", "Giulia")])
    scena.utente.send.reset_mock()
    i = scena.staff(canale)
    await scena.cog.dm_chiudi.callback(scena.cog, i, "risolto")

    assert (await modmail_repo.aperta_dell_utente(ID_UTENTE)) is None
    testo_dm = scena.utente.send.await_args.args[0]
    assert "risolto" in testo_dm
    assert "file" not in scena.utente.send.await_args.kwargs  # nessun transcript in DM
    scena.log.send.assert_awaited_once()
    azioni = await clean_db.fetch("SELECT * FROM scheduled_actions WHERE action_type = $1", modulo.MODMAIL_DELETE_ACTION_TYPE)
    assert len(azioni) == 1
    canale.delete.assert_not_awaited()
    i.followup.send.assert_awaited_once()


def _storia(righe):
    async def gen(**kw):
        for testo, autore in righe:
            yield SimpleNamespace(
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc), author=autore,
                content=testo, attachments=[], embeds=[],
            )

    return gen


async def test_dm_chiudi_non_per_utenti_normali(scena):
    canale = await _con_conversazione(scena)
    i = scena.staff(canale, manage_guild=False)
    await scena.cog.dm_chiudi.callback(scena.cog, i, None)
    assert (await modmail_repo.aperta_dell_utente(ID_UTENTE)) is not None


async def test_canale_cancellato_a_mano_libera_l_utente(scena):
    canale = await _con_conversazione(scena)
    await scena.cog.on_guild_channel_delete(canale)
    assert await modmail_repo.aperta_dell_utente(ID_UTENTE) is None
    await scena.cog.on_message(scena.dm("riprovo"))
    assert len(scena.canali) == 2


async def test_dm_dopo_canale_sparito_senza_evento_chiude_e_non_perde_l_utente(scena):
    canale = await _con_conversazione(scena)
    scena.bot.get_channel = lambda cid: None
    scena.bot.fetch_channel = AsyncMock(side_effect=discord.NotFound(SimpleNamespace(status=404, reason="x"), "x"))
    await scena.cog.on_message(scena.dm("ci sei?"))
    assert await modmail_repo.aperta_dell_utente(ID_UTENTE) is None


async def test_utente_che_lascia_il_server_chiude_la_conversazione(scena):
    canale = await _con_conversazione(scena)
    scena.utente.guild = scena.guild
    await scena.cog.on_member_remove(scena.utente)
    assert await modmail_repo.aperta_dell_utente(ID_UTENTE) is None


async def test_handler_dello_scheduler_elimina_il_canale_e_ignora_il_404(scena):
    canale = await _con_conversazione(scena)
    await scena.cog.handle_modmail_delete_channel(ID_SERVER, ID_UTENTE, {"channel_id": canale.id, "reason": "x"})
    canale.delete.assert_awaited_once()
    canale.delete.side_effect = discord.NotFound(SimpleNamespace(status=404, reason="x"), "x")
    await scena.cog.handle_modmail_delete_channel(ID_SERVER, ID_UTENTE, {"channel_id": canale.id})


# ---------------------------------------------------------------- comandi di gestione
async def test_dm_attiva_richiede_la_categoria_e_dm_disattiva_la_toglie(scena):
    i = scena.staff(fake_text_channel(1, "x"))
    await scena.cog.dm.callback(scena.cog, i, True, None)
    assert "categoria" in i.response.send_message.await_args.args[0]
    assert await modmail_repo.categoria(ID_SERVER) is None
    i = scena.staff(fake_text_channel(1, "x"))
    await scena.cog.dm.callback(scena.cog, i, True, scena.categoria)
    assert await modmail_repo.categoria(ID_SERVER) == ID_CATEGORIA
    await scena.cog.dm.callback(scena.cog, scena.staff(fake_text_channel(1, "x")), False, None)
    assert await modmail_repo.categoria(ID_SERVER) is None


async def test_bloccare_un_utente_chiude_la_conversazione_e_impedisce_di_riaprirla(scena):
    canale = await _con_conversazione(scena)
    i = scena.staff(canale)
    await scena.cog.dm_blocca.callback(scena.cog, i, scena.utente, True)
    assert await modmail_repo.aperta_dell_utente(ID_UTENTE) is None
    assert await modmail_repo.bloccato(ID_SERVER, ID_UTENTE)
    await scena.cog.on_message(scena.dm("posso?"))
    assert len(scena.canali) == 1


async def test_i_comandi_stanno_nei_gruppi_e_sotto_i_25_figli(scena):
    from discord.ext import commands as ext

    bot = ext.Bot(command_prefix="!", intents=discord.Intents.default())
    await modulo.setup(bot)
    try:
        assert {"rispondi", "dm-chiudi"} <= percorsi_del_gruppo("ticket")
        assert {"ticket dm", "ticket dm-blocca"} <= percorsi_del_gruppo("gestione")
        assert len({p for p in percorsi_del_gruppo("gestione") if p.startswith("ticket ")}) <= 25
        assert len(percorsi_del_gruppo("ticket")) <= 25
    finally:
        for cog in list(bot.cogs):
            await bot.remove_cog(cog)
