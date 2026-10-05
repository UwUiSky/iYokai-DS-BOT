"""
tests/test_tickets_correzioni.py
================================
Correzioni al sistema di ticket (issue #62, voci M 6.x).

Database vero (clean_db) e repository veri. I ticket si aprono con il
codice di produzione (`_open_ticket_channel`, lo stesso del bottone
"Apri Ticket"); di Discord ci sono solo i finti fedeli di
tests/support/discord_fakes.py.
"""

from unittest.mock import MagicMock, create_autospec

import discord
import pytest
from discord import app_commands
from discord.ext import commands

import cogs.tickets.tickets as modulo
from cogs.tickets.tickets import TicketsCog, _open_ticket_channel
from core.database import db
from core.repositories.ticket_repo import ticket_repo
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_member,
    fake_role,
    fake_text_channel,
)

ID_SERVER = 100
ID_UTENTE = 20
ID_STAFF = 30
ID_RUOLO_SUPPORTO = 500
ID_CATEGORIA = 900


@pytest.fixture(autouse=True)
async def _ambiente(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    await db.set_module_active_for_guild(ID_SERVER, modulo.MODULE_TICKETS, True)
    yield
    database_module.db._modules_cache.clear()


def _errore_http(stato: int = 400) -> discord.HTTPException:
    return discord.HTTPException(MagicMock(status=stato, reason="errore"), "errore finto")


class Server:
    """Un server finto con una categoria che crea canali numerati da 1000."""

    def __init__(self) -> None:
        self.guild = fake_guild(ID_SERVER)
        self.guild.default_role = fake_role(role_id=ID_SERVER, name="@everyone", position=0)
        self.categoria = create_autospec(discord.CategoryChannel, instance=True)
        self.categoria.id = ID_CATEGORIA
        self.canali: list = []
        self.categoria.create_text_channel.side_effect = self._crea_canale

    async def _crea_canale(self, name, **kwargs):
        canale = fake_text_channel(1000 + len(self.canali), name)
        canale.guild = self.guild
        self.canali.append(canale)
        return canale

    def utente(self, user_id: int = ID_UTENTE, *, ruoli=None, manage_guild: bool = False):
        membro = fake_member(
            user_id,
            roles=ruoli or [],
            guild_permissions=discord.Permissions(manage_guild=manage_guild),
        )
        membro.guild = self.guild
        return membro

    def staff(self):
        return self.utente(ID_STAFF, manage_guild=True)

    def interazione(self, utente=None, canale=None):
        return fake_interaction(
            guild=self.guild, user=utente or self.utente(), channel=canale
        )

    async def apri_ticket(self, utente=None, etichetta=None):
        """Apre un ticket come fa il bottone del pannello. Restituisce il canale."""
        interazione = self.interazione(utente)
        await _open_ticket_channel(interazione, self.guild, self.categoria, etichetta)
        return self.canali[-1]


def _testo(chiamata) -> str:
    return chiamata.args[0] if chiamata.args else chiamata.kwargs.get("content", "")


# ====================================================================
# M 6.6 — claim, priority, add e remove sono riservati allo staff
# ====================================================================
async def _claim(cog, interazione, membro):
    await cog.claim.callback(cog, interazione)


async def _priority(cog, interazione, membro):
    await cog.priority.callback(cog, interazione, app_commands.Choice(name="urgent", value="urgent"))


async def _add(cog, interazione, membro):
    await cog.add.callback(cog, interazione, membro)


async def _remove(cog, interazione, membro):
    await cog.remove.callback(cog, interazione, membro)


COMANDI_STAFF = {"claim": _claim, "priority": _priority, "add": _add, "remove": _remove}


@pytest.mark.parametrize("nome", COMANDI_STAFF)
async def test_chi_ha_aperto_il_ticket_non_puo_usare_i_comandi_dello_staff(nome):
    server = Server()
    canale = await server.apri_ticket()
    interazione = server.interazione(server.utente(), canale)
    cog = TicketsCog(bot=None)

    await COMANDI_STAFF[nome](cog, interazione, server.utente(77))

    risposta = interazione.response.send_message.call_args
    assert "Solo lo staff" in _testo(risposta)
    assert risposta.kwargs["ephemeral"] is True
    canale.set_permissions.assert_not_awaited()
    ticket = await ticket_repo.get_ticket_by_channel(canale.id)
    assert ticket.claimed_by is None
    assert ticket.priority == "normal"


@pytest.mark.parametrize("nome", COMANDI_STAFF)
async def test_lo_staff_puo_usare_i_comandi(nome):
    server = Server()
    canale = await server.apri_ticket()
    interazione = server.interazione(server.staff(), canale)
    cog = TicketsCog(bot=None)

    await COMANDI_STAFF[nome](cog, interazione, server.utente(77))

    assert "Solo lo staff" not in _testo(interazione.response.send_message.call_args)
    ticket = await ticket_repo.get_ticket_by_channel(canale.id)
    if nome == "claim":
        assert ticket.claimed_by == ID_STAFF
    elif nome == "priority":
        assert ticket.priority == "urgent"
    else:
        canale.set_permissions.assert_awaited_once()


async def test_un_ruolo_di_supporto_puo_prendere_in_carico():
    server = Server()
    canale = await server.apri_ticket()
    cog = TicketsCog(bot=None)
    admin = server.interazione(server.staff())
    ruolo = fake_role(ID_RUOLO_SUPPORTO, "Supporto")
    await cog.ticket_support_role_add.callback(cog, admin, ruolo)

    operatore = server.utente(40, ruoli=[ruolo])
    await cog.claim.callback(cog, server.interazione(operatore, canale))

    assert (await ticket_repo.get_ticket_by_channel(canale.id)).claimed_by == 40


@pytest.mark.parametrize("nome", ("add", "remove"))
async def test_add_e_remove_errore_di_discord_risposta_chiara(nome):
    server = Server()
    canale = await server.apri_ticket()
    canale.set_permissions.side_effect = _errore_http(403)
    interazione = server.interazione(server.staff(), canale)
    cog = TicketsCog(bot=None)

    await COMANDI_STAFF[nome](cog, interazione, server.utente(77))

    assert "Non sono riuscito" in _testo(interazione.response.send_message.call_args)


# ====================================================================
# M 6.7 — /ticket-support-role remove toglie anche il ruolo storico
# ====================================================================
async def test_remove_toglie_il_ruolo_impostato_con_ticket_setup():
    server = Server()
    ruolo = fake_role(ID_RUOLO_SUPPORTO, "Supporto")
    server.guild.get_role.side_effect = lambda role_id: ruolo if role_id == ID_RUOLO_SUPPORTO else None
    cog = TicketsCog(bot=None)
    # Il ruolo "storico" lo scrive /ticket-setup.
    await cog.ticket_setup.callback(cog, server.interazione(server.staff()), server.categoria, ruolo)
    assert await modulo._support_role_ids(ID_SERVER) == [ID_RUOLO_SUPPORTO]

    await cog.ticket_support_role_remove.callback(cog, server.interazione(server.staff()), ruolo)

    assert await modulo._support_role_ids(ID_SERVER) == []
    # Il ruolo non vede più i ticket nuovi…
    await server.apri_ticket()
    permessi = server.categoria.create_text_channel.call_args.kwargs["overwrites"]
    assert ruolo not in permessi
    # …e chi lo ha non è più staff.
    operatore = server.interazione(server.utente(40, ruoli=[ruolo]))
    assert await modulo._is_ticket_staff(operatore) is False


async def test_remove_del_ruolo_storico_non_lascia_un_null_nella_configurazione():
    """Un `null` nell'export verrebbe poi rifiutato da /config import."""
    server = Server()
    ruolo = fake_role(ID_RUOLO_SUPPORTO, "Supporto")
    cog = TicketsCog(bot=None)
    await cog.ticket_setup.callback(cog, server.interazione(server.staff()), server.categoria, ruolo)

    await cog.ticket_support_role_remove.callback(cog, server.interazione(server.staff()), ruolo)

    impostazioni = (await db.get_full_config(ID_SERVER))["settings"]
    assert modulo.SETTING_SUPPORT_ROLE not in impostazioni


async def test_remove_di_un_ruolo_non_configurato_lo_dice():
    server = Server()
    cog = TicketsCog(bot=None)
    interazione = server.interazione(server.staff())

    await cog.ticket_support_role_remove.callback(cog, interazione, fake_role(123, "Altro"))

    assert "non è tra i ruoli di supporto" in _testo(interazione.response.send_message.call_args)


# ====================================================================
# M 6.5 — un canale cancellato a mano chiude il ticket
# ====================================================================
async def test_canale_cancellato_a_mano_l_utente_puo_riaprire():
    server = Server()
    primo = await server.apri_ticket()
    cog = TicketsCog(bot=None)

    await cog.on_guild_channel_delete(primo)

    ticket = await ticket_repo.get_ticket_by_channel(primo.id)
    assert ticket.status == "closed"
    assert ticket.closed_at is not None
    assert ticket.closed_by is None  # non sappiamo chi ha cancellato il canale
    secondo = await server.apri_ticket()
    assert secondo.id != primo.id
    assert (await ticket_repo.get_ticket_by_channel(secondo.id)).status == "open"


async def test_canale_qualunque_cancellato_non_tocca_i_ticket():
    server = Server()
    canale = await server.apri_ticket()
    cog = TicketsCog(bot=None)

    await cog.on_guild_channel_delete(fake_text_channel(424242, "altro"))

    assert (await ticket_repo.get_ticket_by_channel(canale.id)).status == "open"


async def test_canale_di_un_ticket_gia_chiuso_non_cambia_chi_lo_ha_chiuso():
    server = Server()
    canale = await server.apri_ticket()
    await ticket_repo.close_ticket(canale.id, ID_STAFF)
    cog = TicketsCog(bot=None)

    await cog.on_guild_channel_delete(canale)

    assert (await ticket_repo.get_ticket_by_channel(canale.id)).closed_by == ID_STAFF


# ====================================================================
# M 6.1 — categorie: tetto di 25, etichetta fino a 100, emoji controllata
# ====================================================================
def _categoria_discord(category_id: int = ID_CATEGORIA):
    categoria = create_autospec(discord.CategoryChannel, instance=True)
    categoria.id = category_id
    categoria.name = "Ticket"
    return categoria


async def _aggiungi(cog, server, etichetta: str, emoji=None):
    interazione = server.interazione(server.staff())
    await cog.ticket_category_add.callback(cog, interazione, etichetta, _categoria_discord(), emoji)
    return _testo(interazione.response.send_message.call_args)


async def _premi_apri_ticket(server, utente=None):
    """Preme il bottone "Apri Ticket" del pannello. Restituisce l'interazione."""
    interazione = server.interazione(utente)
    await modulo.TicketPanelView().open_ticket.callback(interazione)
    return interazione


def _opzioni_del_menu(interazione) -> list[dict]:
    vista = interazione.response.send_message.call_args.kwargs["view"]
    return vista.to_components()[0]["components"][0]["options"]


async def test_ticket_category_add_dichiara_i_limiti_delle_opzioni():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await bot.add_cog(TicketsCog(bot))

    gruppo = bot.tree.get_command("ticket-category")
    for nome in ("add", "remove"):
        opzioni = {o["name"]: o for o in gruppo.get_command(nome).to_dict(bot.tree)["options"]}
        assert opzioni["label"]["min_length"] == 1
        assert opzioni["label"]["max_length"] == 100
    opzioni = {o["name"]: o for o in gruppo.get_command("add").to_dict(bot.tree)["options"]}
    assert opzioni["emoji"]["max_length"] <= 100


async def test_la_ventiseiesima_categoria_viene_rifiutata():
    server = Server()
    cog = TicketsCog(bot=None)
    for numero in range(25):
        assert "impostata" in await _aggiungi(cog, server, f"Categoria {numero:02d}")

    risposta = await _aggiungi(cog, server, "Una di troppo")

    assert "25" in risposta
    assert len(await ticket_repo.list_categories(ID_SERVER)) == 25
    # Aggiornare una categoria che esiste già resta possibile.
    assert "impostata" in await _aggiungi(cog, server, "Categoria 03", "🛠️")


@pytest.mark.parametrize("emoji", ["ciao", ":smile:", "1", "<:rotta>", "🎫 ticket"])
async def test_un_testo_che_non_e_un_emoji_viene_rifiutato(emoji):
    server = Server()
    cog = TicketsCog(bot=None)

    risposta = await _aggiungi(cog, server, "Supporto", emoji)

    assert "emoji" in risposta.lower()
    assert await ticket_repo.list_categories(ID_SERVER) == []


@pytest.mark.parametrize(
    "emoji", ["🎫", "🛠️", "🇮🇹", "1️⃣", "👨‍👩‍👧", "<:yokai:123456789012345678>", "<a:gira:123456789012345678>"]
)
async def test_le_emoji_vere_sono_accettate(emoji):
    server = Server()
    cog = TicketsCog(bot=None)

    assert "impostata" in await _aggiungi(cog, server, "Supporto", emoji)

    assert (await ticket_repo.list_categories(ID_SERVER))[0].emoji == emoji


async def test_il_menu_si_costruisce_anche_con_dati_vecchi_fuori_limite():
    """
    Dati salvati prima di questi controlli: 30 categorie, un'etichetta
    di 150 caratteri, un testo che non è un'emoji. Il menu deve uscire
    lo stesso, dentro i limiti di Discord.
    """
    server = Server()
    for numero in range(28):
        await ticket_repo.add_category(ID_SERVER, f"Categoria {numero:02d}", ID_CATEGORIA, "🎫")
    await ticket_repo.add_category(ID_SERVER, "A" * 150, ID_CATEGORIA, "non-emoji")
    await ticket_repo.add_category(ID_SERVER, "B" * 150, ID_CATEGORIA, None)

    interazione = await _premi_apri_ticket(server)

    opzioni = _opzioni_del_menu(interazione)
    assert len(opzioni) == 25
    assert all(1 <= len(o["label"]) <= 100 for o in opzioni)
    assert all(1 <= len(o["value"]) <= 100 for o in opzioni)
    assert len({o["value"] for o in opzioni}) == 25
    lunga = next(o for o in opzioni if o["label"].startswith("AAAA"))
    assert "emoji" not in lunga


async def test_emoji_rifiutata_da_discord_il_menu_esce_senza_emoji():
    """Un'emoji personalizzata cancellata o di un altro server: errore 400."""
    server = Server()
    cog = TicketsCog(bot=None)
    await _aggiungi(cog, server, "Supporto", "<:sparita:123456789012345678>")
    interazione = server.interazione()
    interazione.response.send_message.side_effect = [_errore_http(400), None]

    await modulo.TicketPanelView().open_ticket.callback(interazione)

    assert interazione.response.send_message.await_count == 2
    opzioni = _opzioni_del_menu(interazione)
    assert [o["label"] for o in opzioni] == ["Supporto"]
    assert "emoji" not in opzioni[0]


async def test_scegliere_una_categoria_dal_menu_apre_il_ticket_li():
    server = Server()
    server.guild.get_channel.side_effect = (
        lambda channel_id: server.categoria if channel_id == ID_CATEGORIA else None
    )
    # isinstance(…, CategoryChannel) deve valere per la categoria finta.
    cog = TicketsCog(bot=None)
    await _aggiungi(cog, server, "Supporto tecnico", "🛠️")
    pannello = await _premi_apri_ticket(server)
    vista = pannello.response.send_message.call_args.kwargs["view"]
    menu = vista.children[0]
    scelta = server.interazione()
    menu._refresh_state(scelta, {"values": [_opzioni_del_menu(pannello)[0]["value"]]})

    await menu.callback(scelta)

    assert len(server.canali) == 1
    ticket = await ticket_repo.get_ticket_by_channel(server.canali[0].id)
    assert ticket.category_label == "Supporto tecnico"


async def test_etichetta_vecchia_lunghissima_il_benvenuto_resta_un_embed_valido():
    server = Server()

    canale = await server.apri_ticket(etichetta="E" * 3000)

    campo = canale.send.call_args.kwargs["embed"].fields[0]
    assert campo.name == "Categoria"
    assert len(campo.value) <= 1024


async def test_elenco_di_25_categorie_lunghe_resta_in_un_messaggio_valido():
    server = Server()
    cog = TicketsCog(bot=None)
    for numero in range(25):
        await _aggiungi(cog, server, f"{numero:02d}" + "c" * 98, "🎫")
    interazione = server.interazione(server.staff())

    await cog.ticket_category_list.callback(cog, interazione)

    chiamata = interazione.response.send_message.call_args
    assert len(_testo(chiamata)) <= 2000
    embed = chiamata.kwargs["embed"]
    assert len(embed.description) <= 4096
    assert embed.description.count("<#") == 25


async def test_elenco_con_emoji_personalizzate_lunghe_resta_entro_4096():
    server = Server()
    cog = TicketsCog(bot=None)
    for numero in range(25):
        emoji = f"<a:{'e' * 32}:{10**19 + numero}>"
        await _aggiungi(cog, server, f"{numero:02d}" + "c" * 98, emoji)
    interazione = server.interazione(server.staff())

    await cog.ticket_category_list.callback(cog, interazione)

    embed = interazione.response.send_message.call_args.kwargs["embed"]
    assert len(embed.description) <= 4096
    assert "…e altre" in embed.description


# ====================================================================
# M 6.3 — il canale nasce già con il numero giusto (nessuna rinomina)
# M 6.4 — un solo ticket aperto per utente, anche con due clic insieme
# ====================================================================
async def test_il_canale_nasce_con_il_numero_del_ticket_senza_rinomine():
    server = Server()

    primo = await server.apri_ticket(server.utente(21))
    secondo = await server.apri_ticket(server.utente(22))

    assert [c.name for c in server.canali] == ["ticket-0001", "ticket-0002"]
    primo.edit.assert_not_awaited()
    secondo.edit.assert_not_awaited()
    assert (await ticket_repo.get_ticket_by_channel(primo.id)).ticket_number == 1
    assert (await ticket_repo.get_ticket_by_channel(secondo.id)).ticket_number == 2
    # Il messaggio di benvenuto porta lo stesso numero del canale.
    assert secondo.send.call_args.kwargs["embed"].title == "Ticket #0002"


async def test_creazione_del_canale_fallita_nessun_ticket_nel_database():
    server = Server()
    server.categoria.create_text_channel.side_effect = _errore_http(400)
    interazione = server.interazione()

    await _open_ticket_channel(interazione, server.guild, server.categoria, None)

    assert await ticket_repo.count_open_tickets_for_user(ID_SERVER, ID_UTENTE) == 0
    assert "Impossibile creare" in _testo(interazione.followup.send.call_args)
    # L'utente può riprovare subito.
    server.categoria.create_text_channel.side_effect = server._crea_canale
    await server.apri_ticket()
    assert await ticket_repo.count_open_tickets_for_user(ID_SERVER, ID_UTENTE) == 1


async def test_due_clic_insieme_un_solo_ticket_e_un_solo_canale():
    import asyncio

    server = Server()
    crea_davvero = server._crea_canale

    async def _crea_lentamente(name, **kwargs):
        await asyncio.sleep(0.05)  # il secondo clic arriva mentre Discord crea il canale
        return await crea_davvero(name, **kwargs)

    server.categoria.create_text_channel.side_effect = _crea_lentamente
    primo_clic, secondo_clic = server.interazione(), server.interazione()

    await asyncio.gather(
        _open_ticket_channel(primo_clic, server.guild, server.categoria, None),
        _open_ticket_channel(secondo_clic, server.guild, server.categoria, None),
    )

    assert len(server.canali) == 1
    assert await ticket_repo.count_open_tickets_for_user(ID_SERVER, ID_UTENTE) == 1
    risposte = sorted(
        _testo(clic.followup.send.call_args) for clic in (primo_clic, secondo_clic)
    )
    assert risposte[0].startswith("Sto già aprendo")
    assert risposte[1].startswith("Ticket creato")


async def test_ticket_aperto_da_un_altro_processo_il_canale_in_piu_viene_eliminato():
    """
    Il vincolo del database copre il caso che il controllo in memoria
    non vede (due processi, o un ticket nato tra il controllo e la
    scrittura): il canale appena creato non deve restare orfano.
    """
    server = Server()
    crea_davvero = server._crea_canale

    async def _crea_mentre_un_altro_apre(name, **kwargs):
        await ticket_repo.create_ticket(ID_SERVER, ID_UTENTE, 555_555)
        return await crea_davvero(name, **kwargs)

    server.categoria.create_text_channel.side_effect = _crea_mentre_un_altro_apre
    interazione = server.interazione()

    await _open_ticket_channel(interazione, server.guild, server.categoria, None)

    assert await ticket_repo.count_open_tickets_for_user(ID_SERVER, ID_UTENTE) == 1
    server.canali[0].delete.assert_awaited_once()
    assert await ticket_repo.get_ticket_by_channel(server.canali[0].id) is None
    assert "Hai già un ticket aperto" in _testo(interazione.followup.send.call_args)


async def test_il_database_rifiuta_un_secondo_ticket_aperto_per_lo_stesso_utente():
    from core.repositories.ticket_repo import TicketAlreadyOpenError

    await ticket_repo.create_ticket(ID_SERVER, ID_UTENTE, 1)
    with pytest.raises(TicketAlreadyOpenError):
        await ticket_repo.create_ticket(ID_SERVER, ID_UTENTE, 2)

    # Chiuso il primo, l'utente può aprirne un altro; un altro utente non è toccato.
    await ticket_repo.close_ticket(1, ID_STAFF)
    await ticket_repo.create_ticket(ID_SERVER, ID_UTENTE, 3)
    await ticket_repo.create_ticket(ID_SERVER, 999, 4)
    await ticket_repo.create_ticket(ID_SERVER + 1, ID_UTENTE, 5)


async def test_la_migrazione_chiude_i_doppioni_gia_presenti(clean_db):
    """Un database vero può avere già due ticket aperti dello stesso utente."""
    from pathlib import Path

    migrazione = (
        Path(modulo.__file__).parents[2]
        / "core/migrations/0010_tickets_un_solo_aperto_per_utente.sql"
    )
    await clean_db.execute("DROP INDEX uq_tickets_un_aperto_per_utente")
    for canale in (1, 2, 3):
        await ticket_repo.create_ticket(ID_SERVER, ID_UTENTE, canale)
    await ticket_repo.create_ticket(ID_SERVER, 999, 4)

    await clean_db.execute(migrazione.read_text(encoding="utf-8"))

    aperti = await clean_db.fetch(
        "SELECT channel_id FROM tickets WHERE status = 'open' ORDER BY channel_id"
    )
    # Resta aperto il più recente dell'utente; l'altro utente non cambia.
    assert [r["channel_id"] for r in aperti] == [3, 4]
    chiusi = await clean_db.fetch("SELECT closed_at FROM tickets WHERE status = 'closed'")
    assert len(chiusi) == 2 and all(r["closed_at"] is not None for r in chiusi)


# ====================================================================
# M 6.2 — /ticket rename: nome fino a 100 caratteri
# M 6.3 — sul limite di rinomine: "riprova tra N minuti", nessuna attesa
# ====================================================================
@pytest.fixture
def _rinomine_azzerate():
    from core.channel_rename import rename_tracker

    rename_tracker._renames.clear()
    yield
    rename_tracker._renames.clear()


async def test_ticket_rename_dichiara_da_1_a_100_caratteri():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await bot.add_cog(TicketsCog(bot))

    comando = bot.tree.get_command("ticket").get_command("rename")
    opzioni = {o["name"]: o for o in comando.to_dict(bot.tree)["options"]}

    assert opzioni["name"]["min_length"] == 1
    assert opzioni["name"]["max_length"] == 100


async def _rinomina(cog, server, canale, nome: str):
    interazione = server.interazione(server.utente(), canale)
    await cog.rename.callback(cog, interazione, nome)
    return interazione


async def test_la_terza_rinomina_risponde_subito_riprova_tra(_rinomine_azzerate):
    server = Server()
    canale = await server.apri_ticket()
    cog = TicketsCog(bot=None)

    for nome in ("primo", "secondo"):
        riuscita = await _rinomina(cog, server, canale, nome)
        riuscita.response.defer.assert_awaited_once()
        assert nome in _testo(riuscita.followup.send.call_args)
    terza = await _rinomina(cog, server, canale, "terzo")

    # L'apertura del ticket non ha speso nessuna rinomina: due passano.
    assert [c.kwargs["name"] for c in canale.edit.call_args_list] == ["primo", "secondo"]
    risposta = terza.response.send_message.call_args
    assert "Riprova tra circa 10 minuti" in _testo(risposta)
    assert risposta.kwargs["ephemeral"] is True
    terza.response.defer.assert_not_awaited()


async def test_rinomina_rifiutata_da_discord_risposta_chiara(_rinomine_azzerate):
    server = Server()
    canale = await server.apri_ticket()
    canale.edit.side_effect = _errore_http(403)
    cog = TicketsCog(bot=None)

    interazione = await _rinomina(cog, server, canale, "nuovo-nome")

    assert "Non sono riuscito a rinominare" in _testo(interazione.followup.send.call_args)


async def test_rinomina_con_discord_in_attesa_non_resta_appesa(_rinomine_azzerate, monkeypatch):
    import asyncio

    import core.channel_rename as rinomina

    monkeypatch.setattr(rinomina, "RENAME_TIMEOUT_SECONDS", 0.05)
    server = Server()
    canale = await server.apri_ticket()

    async def _attesa_infinita(**kwargs):
        await asyncio.sleep(600)

    canale.edit.side_effect = _attesa_infinita
    cog = TicketsCog(bot=None)

    interazione = await asyncio.wait_for(_rinomina(cog, server, canale, "nuovo"), timeout=2)

    assert "Riprova tra circa 10 minuti" in _testo(interazione.followup.send.call_args)


async def test_il_nome_nella_risposta_non_puo_menzionare_nessuno(_rinomine_azzerate):
    server = Server()
    canale = await server.apri_ticket()
    cog = TicketsCog(bot=None)

    interazione = await _rinomina(cog, server, canale, "@everyone")

    menzioni = interazione.followup.send.call_args.kwargs["allowed_mentions"]
    assert menzioni.to_dict() == discord.AllowedMentions.none().to_dict()
