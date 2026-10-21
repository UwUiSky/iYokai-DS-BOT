"""
tests/test_ticket_catalogo.py
=============================
#120 (catalogo ticket): motivo di chiusura, rilascia, passa, transcript senza chiudere,
add/remove di un ruolo, chiusura di massa. Database vero; Discord finto.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

import cogs.tickets.tickets as modulo
from cogs.tickets.tickets import TICKET_DELETE_ACTION_TYPE
from core.repositories.ticket_repo import ticket_repo
from core.scheduler import Scheduler
from tests.support.concorrenza import apri_connessioni
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_member,
    fake_role,
    fake_text_channel,
)

GUILD_ID = 100
CANALE = 200
UTENTE = 20
STAFF = 30
MANAGER = 31


@pytest.fixture(autouse=True)
def _pool(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()


@pytest.fixture
async def cog(monkeypatch):
    monkeypatch.setattr(modulo, "scheduler", Scheduler())
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await modulo.setup(bot)
    c = bot.get_cog("TicketsCog")
    c._transcript_senza_bloccare = AsyncMock()
    c._richiedi_voto = AsyncMock()
    yield c
    await bot.close()


def _manager(uid=MANAGER):
    return fake_member(uid, guild_permissions=discord.Permissions(manage_guild=True))


def _inter(user, canale_id=CANALE):
    canale = fake_text_channel(canale_id)
    guild = fake_guild(GUILD_ID)
    return fake_interaction(guild=guild, user=user, channel=canale)


async def _ticket(canale=CANALE, numero=1, utente=UTENTE):
    await ticket_repo.create_ticket(GUILD_ID, utente, canale, ticket_number=numero)


def _testo(inter) -> str:
    return str(inter.response.send_message.call_args)


async def test_close_salva_il_motivo(cog):
    await _ticket()
    inter = _inter(fake_member(UTENTE))
    await cog.close.callback(cog, inter, "Risolto via DM")
    t = await ticket_repo.get_ticket_by_channel(CANALE)
    assert t.status == "closed" and t.close_reason == "Risolto via DM"
    assert "Risolto via DM" in _testo(inter)


async def test_forceclose_salva_il_motivo(cog, monkeypatch):
    await _ticket()
    cog._elimina_canale = AsyncMock()
    inter = _inter(_manager())
    await cog.forceclose.callback(cog, inter, "Spam")
    t = await ticket_repo.get_ticket_by_channel(CANALE)
    assert t.close_reason == "Spam"


async def test_il_transcript_riporta_il_motivo(cog):
    await _ticket()
    await ticket_repo.close_ticket(CANALE, 1, reason="Duplicato")
    t = await ticket_repo.get_ticket_by_channel(CANALE)
    canale = fake_text_channel(CANALE)

    async def vuota(**_):
        return
        yield

    canale.history = MagicMock(side_effect=lambda **kw: vuota())
    testo = await cog._build_transcript_text(canale, t)
    assert "Motivo di chiusura: Duplicato" in testo


async def test_rilascia_solo_chi_lo_ha_preso_o_manage_guild(cog):
    await _ticket()
    await ticket_repo.claim_ticket(CANALE, STAFF)
    estraneo = fake_member(
        40, roles=[fake_role(role_id=7)], guild_permissions=discord.Permissions.none()
    )
    # 40 non e' staff: rifiutato prima ancora del controllo del reclamante
    inter = _inter(estraneo)
    await cog.rilascia.callback(cog, inter)
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).claimed_by == STAFF

    # un altro membro dello staff (manage_guild) puo'
    inter = _inter(_manager())
    await cog.rilascia.callback(cog, inter)
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).claimed_by is None


async def test_rilascia_rifiuta_un_collega_con_solo_ruolo_di_supporto(cog, monkeypatch):
    await _ticket()
    await ticket_repo.claim_ticket(CANALE, STAFF)
    monkeypatch.setattr(modulo, "_support_role_ids", AsyncMock(return_value=[7]))
    collega = fake_member(41, roles=[fake_role(role_id=7)])
    inter = _inter(collega)
    await cog.rilascia.callback(cog, inter)
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).claimed_by == STAFF
    assert "Solo chi" in _testo(inter)


async def test_rilascia_su_ticket_non_preso(cog):
    await _ticket()
    inter = _inter(_manager())
    await cog.rilascia.callback(cog, inter)
    assert "Nessuno" in _testo(inter)


async def test_passa_solo_a_un_membro_dello_staff(cog, monkeypatch):
    await _ticket()
    monkeypatch.setattr(modulo, "_support_role_ids", AsyncMock(return_value=[7]))
    inter = _inter(_manager())
    semplice = fake_member(50)
    await cog.passa.callback(cog, inter, semplice)
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).claimed_by is None

    bot_staff = fake_member(51, bot=True, guild_permissions=discord.Permissions(manage_guild=True))
    await cog.passa.callback(cog, _inter(_manager()), bot_staff)
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).claimed_by is None

    collega = fake_member(52, roles=[fake_role(role_id=7)])
    await cog.passa.callback(cog, _inter(_manager()), collega)
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).claimed_by == 52


async def test_transcript_solo_staff_e_il_ticket_resta_aperto(cog):
    await _ticket()
    cog._build_transcript_text = AsyncMock(return_value="ciao")
    inter = _inter(fake_member(UTENTE))
    await cog.transcript.callback(cog, inter)
    assert "Solo lo staff" in _testo(inter)
    cog._build_transcript_text.assert_not_called()

    inter = _inter(_manager())
    await cog.transcript.callback(cog, inter)
    inter.followup.send.assert_called()
    assert (await ticket_repo.get_ticket_by_channel(CANALE)).status == "open"


async def test_add_e_remove_ruolo_ma_mai_everyone(cog):
    await _ticket()
    ruolo = fake_role(role_id=7)
    inter = _inter(_manager())
    inter.channel.set_permissions = AsyncMock()
    await cog.add.callback(cog, inter, None, ruolo)
    inter.channel.set_permissions.assert_awaited_once()
    assert inter.channel.set_permissions.await_args.args[0] is ruolo

    inter = _inter(_manager())
    inter.channel.set_permissions = AsyncMock()
    await cog.remove.callback(cog, inter, None, ruolo)
    inter.channel.set_permissions.assert_awaited_once_with(ruolo, overwrite=None)

    everyone = fake_role(role_id=GUILD_ID)
    inter = _inter(_manager())
    inter.channel.set_permissions = AsyncMock()
    await cog.add.callback(cog, inter, None, everyone)
    inter.channel.set_permissions.assert_not_called()


async def test_add_vuole_esattamente_uno_tra_utente_e_ruolo(cog):
    await _ticket()
    inter = _inter(_manager())
    inter.channel.set_permissions = AsyncMock()
    await cog.add.callback(cog, inter, None, None)
    await cog.add.callback(cog, inter, fake_member(60), fake_role(role_id=7))
    inter.channel.set_permissions.assert_not_called()


async def test_chiudi_tutti_ne_chiude_al_massimo_25_e_dice_quanti_restano(cog, monkeypatch):
    totale = modulo.MAX_CHIUSURA_DI_MASSA + 3
    guild = fake_guild(GUILD_ID)
    guild.me = fake_member(999, bot=True)
    canali = {}
    for i in range(totale):
        await _ticket(canale=1000 + i, numero=i + 1, utente=500 + i)
        canali[1000 + i] = fake_text_channel(1000 + i)
    guild.get_channel = MagicMock(side_effect=lambda cid: canali.get(cid))
    inter = fake_interaction(guild=guild, user=_manager(), channel=fake_text_channel(1))
    await cog.chiudi_tutti.callback(cog, inter, "Fine evento")

    chiusi = await ticket_repo._pool.fetch("SELECT close_reason FROM tickets WHERE status = 'closed'")
    assert len(chiusi) == modulo.MAX_CHIUSURA_DI_MASSA
    assert {r["close_reason"] for r in chiusi} == {"Fine evento"}
    azioni = await ticket_repo._pool.fetch(
        "SELECT 1 FROM scheduled_actions WHERE action_type = $1", TICKET_DELETE_ACTION_TYPE
    )
    assert len(azioni) == modulo.MAX_CHIUSURA_DI_MASSA
    assert "ne restano 3" in str(inter.followup.send.call_args).lower()


# ====================================================================
# Cacciatore-bug: chiusura idempotente, atomicita', uscita, embed, ruoli, chiudi-tutti
# ====================================================================


async def test_due_close_insieme_fanno_un_solo_transcript_voto_ed_eliminazione(cog, clean_db):
    await apri_connessioni(clean_db, 4)
    await _ticket()
    i1, i2 = _inter(fake_member(UTENTE)), _inter(fake_member(UTENTE))
    await asyncio.gather(cog.close.callback(cog, i1, None), cog.close.callback(cog, i2, None))
    assert cog._transcript_senza_bloccare.await_count == 1
    assert cog._richiedi_voto.await_count == 1
    azioni = await clean_db.fetch("SELECT 1 FROM scheduled_actions WHERE action_type = $1", TICKET_DELETE_ACTION_TYPE)
    assert len(azioni) == 1
    risposte = [str(i.response.send_message.call_args) for i in (i1, i2)]
    assert sum("già stato chiuso" in r for r in risposte) == 1


async def test_close_se_il_ticket_si_chiude_dopo_la_lettura_dice_gia_chiuso(cog, monkeypatch):
    # Causa dell'instabilità del test sopra: l'altro close chiudeva il ticket tra due letture.
    await _ticket()
    vera = ticket_repo.get_ticket_by_channel
    letture = []

    async def lettura_poi_chiusura(channel_id):
        t = await vera(channel_id)
        letture.append(t)
        if len(letture) == 1:
            await ticket_repo.close_ticket(channel_id, MANAGER)
        return t

    monkeypatch.setattr(modulo.ticket_repo, "get_ticket_by_channel", lettura_poi_chiusura)
    i = _inter(fake_member(UTENTE))
    await cog.close.callback(cog, i, None)
    assert "già stato chiuso" in _testo(i)
    cog._transcript_senza_bloccare.assert_not_awaited()


async def test_se_la_pianificazione_fallisce_il_ticket_resta_aperto(cog, monkeypatch):
    await _ticket()
    monkeypatch.setattr(modulo.scheduler, "schedule", AsyncMock(side_effect=RuntimeError("db giù")))
    with pytest.raises(RuntimeError):
        await cog.close.callback(cog, _inter(fake_member(UTENTE)), "motivo")
    t = await ticket_repo.get_ticket_by_channel(CANALE)
    assert t.status == "open" and t.close_reason is None


async def test_forceclose_su_ticket_gia_chiuso_non_ripete_transcript_e_voto(cog):
    await _ticket()
    await ticket_repo.close_ticket(CANALE, 1)
    cog._elimina_canale = AsyncMock()
    await cog.forceclose.callback(cog, _inter(_manager()), None)
    cog._transcript_senza_bloccare.assert_not_awaited()
    cog._richiedi_voto.assert_not_awaited()
    cog._elimina_canale.assert_awaited_once()


async def test_chi_esce_chiude_anche_il_ticket_senza_pannello_e_il_motivo_si_salva(cog):
    await _ticket()  # ticket classico: nessun panel_id
    guild = fake_guild(GUILD_ID)
    guild.me = fake_member(999, bot=True)
    canale = fake_text_channel(CANALE)
    guild.get_channel = MagicMock(return_value=canale)
    uscito = fake_member(UTENTE)
    uscito.guild = guild
    await cog.on_member_remove(uscito)
    t = await ticket_repo.get_ticket_by_channel(CANALE)
    assert t.status == "closed" and "lasciato il server" in t.close_reason


async def test_il_benvenuto_con_cinque_risposte_lunghe_resta_sotto_6000_e_il_ticket_nasce(cog):
    from core import ticket_form_logic as form
    from core.repositories.ticket_form_repo import ticket_form_repo

    p = await ticket_form_repo.crea_pannello(GUILD_ID, "Supporto", 1, "Supporto")
    p = SimpleNamespace(**{**p.__dict__, "welcome_text": "B" * 1000, "autoclose_minutes": None, "sollecito_minuti": None})
    domande = [SimpleNamespace(label="D" * 256, required=True) for _ in range(5)]
    campi = form.campi_risposte(domande, ["R" * 5000] * 5)

    guild = fake_guild(GUILD_ID)
    guild.default_role = fake_role(role_id=GUILD_ID, name="@everyone", position=0)
    canale = fake_text_channel(CANALE)
    categoria = MagicMock(spec=discord.CategoryChannel)
    categoria.create_text_channel = AsyncMock(return_value=canale)
    i = fake_interaction(guild=guild, user=fake_member(UTENTE))
    await modulo._open_ticket_channel(i, guild, categoria, "C" * 100, panel=p, campi=campi)
    embed = canale.send.await_args.kwargs["embed"]
    assert len(embed) <= 6000
    assert len(embed.fields) == len(campi) + 1  # tutte le risposte + la categoria


async def test_remove_rifiuta_il_ruolo_di_supporto_e_quello_del_bot(cog, monkeypatch):
    await _ticket()
    monkeypatch.setattr(modulo, "_support_role_ids", AsyncMock(return_value=[7]))
    for ruolo in (fake_role(role_id=7), fake_role(role_id=8, managed=True)):
        inter = _inter(_manager())
        inter.channel.set_permissions = AsyncMock()
        await cog.remove.callback(cog, inter, None, ruolo)
        inter.channel.set_permissions.assert_not_called()
        assert "bloccherebbe" in _testo(inter)


async def test_chiudi_tutti_non_pinga_nessuno_e_manda_avvisi_di_avanzamento(cog):
    guild = fake_guild(GUILD_ID)
    guild.me = fake_member(999, bot=True)
    canali = {}
    for n in range(6):
        await _ticket(canale=1000 + n, numero=n + 1, utente=500 + n)
        canali[1000 + n] = fake_text_channel(1000 + n)
    guild.get_channel = MagicMock(side_effect=lambda cid: canali.get(cid))
    inter = fake_interaction(guild=guild, user=_manager(), channel=fake_text_channel(1))
    await cog.chiudi_tutti.callback(cog, inter, "<@123> fine")
    for c in canali.values():
        assert c.send.await_args.kwargs["allowed_mentions"].users is False
    messaggi = [str(c) for c in inter.followup.send.call_args_list]
    assert any("Chiusi finora 5" in m for m in messaggi)
    assert "Chiusi 6" in messaggi[-1]


# ====================================================================
# Giro del capo: chiudi-tutti prosegue, uscita con più ticket, mappa dell'attività
# ====================================================================
async def test_chiudi_tutti_prosegue_oltre_il_ticket_che_solleva_e_lo_dice(cog):
    guild = fake_guild(GUILD_ID)
    guild.me = fake_member(999, bot=True)
    canali = {}
    for n in range(4):
        await _ticket(canale=1000 + n, numero=n + 1, utente=500 + n)
        canali[1000 + n] = fake_text_channel(1000 + n)
    guild.get_channel = MagicMock(side_effect=lambda cid: canali.get(cid))
    vera = cog._chiudi_da_sistema

    async def _a_volte_solleva(guild_, channel, ticket, **kw):
        if channel.id == 1001:
            raise RuntimeError("scheduler giù")
        return await vera(guild_, channel, ticket, **kw)

    cog._chiudi_da_sistema = _a_volte_solleva
    inter = fake_interaction(guild=guild, user=_manager(), channel=fake_text_channel(1))
    await cog.chiudi_tutti.callback(cog, inter, None)

    chiusi = await ticket_repo._pool.fetchval("SELECT count(*) FROM tickets WHERE status = 'closed'")
    assert chiusi == 3
    ultimo = str(inter.followup.send.call_args)
    assert "Chiusi 3" in ultimo and "1 non" in ultimo


async def test_chi_esce_dal_server_con_piu_ticket_aperti_li_vede_chiusi_tutti(cog):
    guild = fake_guild(GUILD_ID)
    guild.me = fake_member(999, bot=True)
    canali = {}
    for n in range(2):
        await ticket_repo.create_ticket(GUILD_ID, 500, 1000 + n, ticket_number=n + 1, max_aperti=2)
        canali[1000 + n] = fake_text_channel(1000 + n)
    guild.get_channel = MagicMock(side_effect=lambda cid: canali.get(cid))
    membro = fake_member(500)
    membro.guild = guild
    await cog.on_member_remove(membro)
    assert await ticket_repo.count_open_tickets_for_user(GUILD_ID, 500) == 0


async def test_la_mappa_dell_attivita_non_cresce_all_infinito(cog, monkeypatch):
    for canale in range(modulo._ATTIVITA_MAX_VOCI + 50):
        cog._attivita_scritta[canale] = -10_000.0  # scritta molto tempo fa
    monkeypatch.setattr(ticket_repo, "touch_activity", AsyncMock())
    await cog._segna_attivita(9_999_999)
    assert len(cog._attivita_scritta) <= 2
    await cog.on_guild_channel_delete(fake_text_channel(9_999_999))
    assert 9_999_999 not in cog._attivita_scritta
