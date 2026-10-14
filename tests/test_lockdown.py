"""
tests/test_lockdown.py
======================
NF-29 (#100): blocco totale del server e modalita' panico.
Blocco, sblocco identico a prima, interruzione a meta', ordini in parallelo,
regole del panico (SIC-011..015) e comandi.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, create_autospec

import discord
import pytest

import cogs.moderation._shared as shared
import cogs.security.lockdown as cog_modulo
from core import channel_router as router
from core import lockdown_logic as logica
from core import lockdown_service as servizio
from core.repositories.lockdown_repo import ConfigBlocco, lockdown_repo
from core.repositories.output_channel_repo import output_channel_repo
from core.repositories.security_repo import security_repo
from core.security_logic import AntiNukeConfig, TRUST_LEVEL_TRUSTED, TrustEntry
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role

GUILD_ID = 7100
PROPRIETARIO = 555


# ---------------------------------------------------------------- finti
def _canale(classe, channel_id, **kw):
    # create_autospec non dà un isinstance sulla classe vera con __class__ riassegnato: si usa una sottoclasse.
    class _C(classe):
        def __init__(self):  # niente costruttore di Discord
            pass

    c = _C()
    c.id = channel_id
    c.name = kw.get("name", f"canale-{channel_id}")
    c.category_id = kw.get("category_id")
    c.ow = kw.get("ow") or discord.PermissionOverwrite()
    c.chiamate = 0
    c.errore = None

    def overwrites_for(target, c=c):
        return discord.PermissionOverwrite.from_pair(*c.ow.pair())

    async def set_permissions(target, *, overwrite=None, reason=None, c=c):
        c.chiamate += 1
        if c.errore is not None:
            raise c.errore
        c.ow = overwrite if overwrite is not None else discord.PermissionOverwrite()

    c.overwrites_for = overwrites_for
    c.pair = lambda c=c: c.ow.pair()
    c.set_permissions = set_permissions
    c.send = AsyncMock()
    return c


def _server(canali):
    server = fake_guild(guild_id=GUILD_ID, owner_id=PROPRIETARIO)
    server.default_role = fake_role(role_id=GUILD_ID, name="@everyone")
    server.channels = canali
    server.get_channel = lambda i: next((c for c in canali if c.id == i), None)
    server.verification_level = discord.VerificationLevel.low
    server.features = []

    async def _edit(*, reason=None, verification_level=None, invites_disabled=None, **resto):
        if verification_level is not None:
            server.verification_level = verification_level
        if invites_disabled is True and "INVITES_DISABLED" not in server.features:
            server.features = server.features + ["INVITES_DISABLED"]
        if invites_disabled is False:
            server.features = [f for f in server.features if f != "INVITES_DISABLED"]

    server.edit = AsyncMock(side_effect=_edit)
    return server


@pytest.fixture(autouse=True)
def db(clean_db, monkeypatch):
    for repo in (lockdown_repo, security_repo, output_channel_repo):
        monkeypatch.setattr(repo, "_pool_provider", lambda: clean_db)
    monkeypatch.setattr(logica, "PAUSA_TRA_GRUPPI", 0)
    monkeypatch.setattr(servizio, "PAUSA_TRA_GRUPPI", 0)
    servizio._panico.clear()
    servizio._da_fermare.clear()
    router._avvisati.clear()
    return clean_db


def _tre_canali():
    testo = _canale(discord.TextChannel, 1, name="generale")
    # Qui @everyone poteva scrivere in modo esplicito: lo sblocco deve rimetterlo cosi'.
    esplicito = _canale(discord.TextChannel, 2, name="annunci", ow=discord.PermissionOverwrite(send_messages=True))
    vocale = _canale(discord.VoiceChannel, 3, name="vocale")
    return testo, esplicito, vocale


# ================================================================== logica
def test_si_bloccano_solo_i_canali_giusti():
    nascosto = _canale(discord.TextChannel, 9, name="___hidden___")
    categoria = _canale(discord.CategoryChannel, 10)
    esclusa = _canale(discord.TextChannel, 11, category_id=77)
    libero = _canale(discord.TextChannel, 12, category_id=78)
    vocale = _canale(discord.VoiceChannel, 13)
    piano = logica.canali_da_bloccare([nascosto, categoria, esclusa, libero, vocale], [77])
    assert [c.id for c, _ in piano] == [12, 13]
    assert dict((c.id, p) for c, p in piano)[13] == logica.PERMESSI_VOCE


def test_ripristina_rimette_solo_il_divieto_del_blocco():
    ow = discord.PermissionOverwrite(send_messages=True, add_reactions=False)
    prima = logica.stato_prima(ow, ("send_messages", "add_reactions"))
    logica.blocca(ow, ("send_messages", "add_reactions"))
    # Dopo il blocco qualcuno ha concesso add_reactions a mano: quella scelta vince.
    ow.add_reactions = True
    rimesso = logica.ripristina(ow, prima)
    assert rimesso.send_messages is True
    assert rimesso.add_reactions is True


def test_overwrite_che_resta_vuoto_si_toglie():
    ow = discord.PermissionOverwrite()
    prima = logica.stato_prima(ow, ("send_messages",))
    logica.blocca(ow, ("send_messages",))
    assert logica.ripristina(ow, prima) is None


def test_chi_agisce_in_panico():
    config = AntiNukeConfig(trust_entries=(TrustEntry(target_id=42, level=TRUST_LEVEL_TRUSTED),))
    assert logica.puo_agire_in_panico(PROPRIETARIO, PROPRIETARIO, config)
    assert logica.puo_agire_in_panico(42, PROPRIETARIO, config)
    assert not logica.puo_agire_in_panico(43, PROPRIETARIO, config)


# ================================================================== servizio
async def test_blocco_e_sblocco_lasciano_il_server_com_era():
    testo, esplicito, vocale = _tre_canali()
    gia = _canale(discord.TextChannel, 4, ow=discord.PermissionOverwrite(send_messages=False, add_reactions=False,
                  send_messages_in_threads=False, create_public_threads=False, create_private_threads=False))
    server = _server([testo, esplicito, vocale, gia])
    prima = {c.id: c.pair() for c in server.channels}

    esito = await servizio.attiva(server, tipo=logica.TIPO_BLOCCO, avviato_da=1, motivo="prova")
    assert esito.ok and esito.bloccati == 3 and esito.saltati >= 1
    assert testo.ow.send_messages is False and vocale.ow.connect is False
    assert gia.chiamate == 0  # gia' bloccato: non si tocca
    assert server.verification_level == discord.VerificationLevel.highest
    assert "INVITES_DISABLED" in server.features

    esito = await servizio.togli(server)
    assert esito.ok
    assert {c.id: c.pair() for c in server.channels} == prima
    assert server.verification_level == discord.VerificationLevel.low
    assert "INVITES_DISABLED" not in server.features
    assert await lockdown_repo.get_stato(GUILD_ID) is None


async def test_categoria_esclusa_non_si_tocca():
    dentro = _canale(discord.TextChannel, 5, category_id=900)
    fuori = _canale(discord.TextChannel, 6, category_id=901)
    server = _server([dentro, fuori])
    await lockdown_repo.save_config(GUILD_ID, ConfigBlocco(categorie_escluse=(900,)))
    await servizio.attiva(server, tipo=logica.TIPO_BLOCCO, avviato_da=1, motivo="prova")
    assert dentro.chiamate == 0
    assert fuori.ow.send_messages is False


async def test_inviti_gia_chiusi_e_verifica_gia_massima_non_si_riaprono():
    testo, _, _ = _tre_canali()
    server = _server([testo])
    server.verification_level = discord.VerificationLevel.highest
    server.features = ["INVITES_DISABLED"]
    await servizio.attiva(server, tipo=logica.TIPO_BLOCCO, avviato_da=1, motivo="prova")
    server.edit.assert_not_awaited()
    await servizio.togli(server)
    assert server.verification_level == discord.VerificationLevel.highest
    assert "INVITES_DISABLED" in server.features


async def test_una_scelta_fatta_a_mano_dopo_il_blocco_vince():
    testo, _, _ = _tre_canali()
    server = _server([testo])
    await servizio.attiva(server, tipo=logica.TIPO_BLOCCO, avviato_da=1, motivo="prova")
    testo.ow.send_messages = True  # un admin riapre solo questo canale
    await servizio.togli(server)
    assert testo.ow.send_messages is True


async def test_interrotto_a_meta_lo_sblocco_riapre_lo_stesso():
    testo, esplicito, vocale = _tre_canali()
    server = _server([testo, esplicito, vocale])
    prima = {c.id: c.pair() for c in server.channels}
    vocale.errore = RuntimeError("il bot si e' fermato")  # non e' un errore di Discord: l'attivazione muore
    with pytest.raises(RuntimeError):
        await servizio.attiva(server, tipo=logica.TIPO_BLOCCO, avviato_da=1, motivo="prova")
    assert (await lockdown_repo.get_stato(GUILD_ID)).stato == logica.STATO_IN_CORSO
    assert vocale.ow.connect is None  # mai toccato, ma la riga di prima c'e' gia'
    vocale.errore = None
    esito = await servizio.togli(server)
    assert esito.ok
    assert {c.id: c.pair() for c in server.channels} == prima
    assert server.verification_level == discord.VerificationLevel.low


async def test_un_canale_che_rifiuta_non_ferma_gli_altri_e_si_dice():
    testo, esplicito, vocale = _tre_canali()
    testo.errore = discord.Forbidden(MagicMock(status=403), "no")
    server = _server([testo, esplicito, vocale])
    esito = await servizio.attiva(server, tipo=logica.TIPO_BLOCCO, avviato_da=1, motivo="prova")
    assert esito.ok and esito.falliti == 1 and esito.bloccati == 2
    assert "non sono riuscito" in esito.messaggio


async def test_togli_mentre_il_blocco_e_in_corso_lo_ferma_e_riapre(monkeypatch):
    canali = [_canale(discord.TextChannel, 100 + i) for i in range(6)]
    server = _server(canali)
    prima = {c.id: c.pair() for c in canali}
    monkeypatch.setattr(servizio, "GRANDEZZA_GRUPPO", 2)
    primo_via = asyncio.Event()
    lascia = asyncio.Event()
    originale = canali[0].set_permissions

    async def lenta(target, **kw):
        primo_via.set()
        await lascia.wait()
        await originale(target, **kw)

    canali[0].set_permissions = lenta
    attivazione = asyncio.create_task(
        servizio.attiva(server, tipo=logica.TIPO_BLOCCO, avviato_da=1, motivo="prova")
    )
    await primo_via.wait()
    sblocco = asyncio.create_task(servizio.togli(server))
    await asyncio.sleep(0)
    lascia.set()
    esito_attiva, esito_togli = await asyncio.gather(attivazione, sblocco)
    assert not esito_attiva.ok and "interrotto" in esito_attiva.messaggio
    assert esito_togli.ok
    assert sum(1 for c in canali if c.chiamate) < 6  # non ha finito il giro
    assert {c.id: c.pair() for c in canali} == prima


async def test_due_blocchi_insieme_ne_partono_uno_solo():
    server = _server([_canale(discord.TextChannel, 1)])
    a, b = await asyncio.gather(
        servizio.attiva(server, tipo=logica.TIPO_BLOCCO, avviato_da=1, motivo="uno"),
        servizio.attiva(server, tipo=logica.TIPO_PANICO, avviato_da=2, motivo="due"),
    )
    assert sorted([a.ok, b.ok]) == [False, True]
    assert server.edit.await_count == 1


async def test_il_riepilogo_va_nel_canale_e_il_panico_avvisa_solo_i_ruoli_scelti():
    testo, _, _ = _tre_canali()
    allarmi = _canale(discord.TextChannel, 808)
    server = _server([testo, allarmi])
    await output_channel_repo.imposta(GUILD_ID, router.TIPO_ALLARMI, 808)
    await lockdown_repo.save_config(GUILD_ID, ConfigBlocco(ruoli_avviso=(31, 32)))
    dove_comando = _canale(discord.TextChannel, 999)
    await servizio.attiva(server, tipo=logica.TIPO_PANICO, avviato_da=1, motivo="prova", riepilogo_in=dove_comando)
    dove_comando.send.assert_awaited_once()
    allarmi.send.assert_awaited_once()
    kw = allarmi.send.await_args.kwargs
    assert "<@&31>" in kw["content"] and "<@&32>" in kw["content"]
    assert not kw["allowed_mentions"].everyone and not kw["allowed_mentions"].users
    assert {r.id for r in kw["allowed_mentions"].roles} == {31, 32}


# ================================================================== panico
async def test_panico_riserva_mod_e_modban_a_proprietario_e_fidati(monkeypatch):
    server = _server([_canale(discord.TextChannel, 1)])
    fidato = 42
    config = AntiNukeConfig(trust_entries=(TrustEntry(target_id=fidato, level=TRUST_LEVEL_TRUSTED),))
    settings = await security_repo.get_settings(GUILD_ID)
    from dataclasses import replace
    await security_repo.save_settings(replace(settings, anti_nuke=config))
    db_finto = MagicMock()
    db_finto.is_module_active_for_guild = AsyncMock(return_value=True)
    monkeypatch.setattr(shared, "db", db_finto)

    def _chi(user_id):
        return fake_interaction(guild=server, user=fake_member(user_id=user_id))

    assert await shared.ensure_module_enabled(_chi(7), "moderation") is True  # niente panico

    await servizio.attiva(server, tipo=logica.TIPO_PANICO, avviato_da=1, motivo="attacco")
    estraneo = _chi(7)
    assert await shared.ensure_module_enabled(estraneo, "moderation") is False
    estraneo.response.send_message.assert_awaited_once()
    assert await shared.ensure_module_enabled(_chi(PROPRIETARIO), "moderation") is True
    assert await shared.ensure_module_enabled(_chi(fidato), "moderation") is True

    await servizio.togli(server)
    assert await shared.ensure_module_enabled(_chi(7), "moderation") is True


async def test_panico_senza_solo_proprietario_non_riserva_nulla():
    server = _server([_canale(discord.TextChannel, 1)])
    await lockdown_repo.save_config(GUILD_ID, ConfigBlocco(solo_proprietario=False))
    await servizio.attiva(server, tipo=logica.TIPO_PANICO, avviato_da=1, motivo="x")
    assert servizio.in_panico(GUILD_ID) and not servizio.panico_riservato(GUILD_ID)


async def test_il_panico_resta_dopo_un_riavvio():
    server = _server([_canale(discord.TextChannel, 1)])
    await servizio.attiva(server, tipo=logica.TIPO_PANICO, avviato_da=1, motivo="x")
    servizio._panico.clear()  # riavvio: la memoria e' vuota
    await servizio.carica_panici()
    assert servizio.panico_riservato(GUILD_ID)


async def test_sblocco_automatico_dopo_i_minuti_scelti():
    server = _server([_canale(discord.TextChannel, 1)])
    await lockdown_repo.save_config(GUILD_ID, ConfigBlocco(sblocco_auto_minuti=30))
    await servizio.attiva(server, tipo=logica.TIPO_PANICO, avviato_da=1, motivo="x")
    stato = await lockdown_repo.get_stato(GUILD_ID)
    assert timedelta(minutes=29) < stato.finisce_il - datetime.now(timezone.utc) <= timedelta(minutes=30)
    assert await lockdown_repo.scaduti(datetime.now(timezone.utc)) == []
    assert await lockdown_repo.scaduti(datetime.now(timezone.utc) + timedelta(minutes=31)) == [GUILD_ID]
    # Il blocco manuale non ha mai una scadenza.
    await servizio.togli(server)
    await servizio.attiva(server, tipo=logica.TIPO_BLOCCO, avviato_da=1, motivo="x")
    assert (await lockdown_repo.get_stato(GUILD_ID)).finisce_il is None


async def test_panico_automatico_parte_solo_se_acceso():
    server = _server([_canale(discord.TextChannel, 1)])
    await servizio.panico_automatico(server, "Anti-Nuke: canali")
    assert await lockdown_repo.get_stato(GUILD_ID) is None
    await lockdown_repo.save_config(GUILD_ID, ConfigBlocco(automatico=True))
    await servizio.panico_automatico(server, "Anti-Nuke: canali")
    await asyncio.gather(*list(servizio._lavori))
    stato = await lockdown_repo.get_stato(GUILD_ID)
    assert stato is not None and stato.tipo == logica.TIPO_PANICO and stato.avviato_da == server.me.id
    # Un secondo attacco non rilancia nulla.
    await servizio.panico_automatico(server, "Anti-Raid")
    assert not servizio._lavori


async def test_panico_automatico_non_rompe_mai_la_difesa(monkeypatch):
    server = _server([])
    monkeypatch.setattr(lockdown_repo, "get_config", AsyncMock(side_effect=RuntimeError("db giu'")))
    await servizio.panico_automatico(server, "Anti-Nuke")  # non solleva


# ================================================================== comandi
@pytest.fixture
def cog():
    return cog_modulo.LockdownCog(MagicMock())


def _comando(server, *, gestisce=True, user_id=PROPRIETARIO):
    utente = fake_member(user_id=user_id)
    utente.guild_permissions = discord.Permissions(manage_guild=gestisce)
    canale = _canale(discord.TextChannel, 999)
    return fake_interaction(guild=server, user=utente, channel=canale)


async def test_blocco_senza_permesso_e_rifiutato(cog):
    server = _server([_canale(discord.TextChannel, 1)])
    i = _comando(server, gestisce=False)
    await cog.blocco_attiva.callback(cog, i, None)
    assert await lockdown_repo.get_stato(GUILD_ID) is None
    i.response.send_message.assert_awaited_once()


async def test_blocco_risponde_subito_con_defer_e_poi_con_il_riepilogo(cog):
    server = _server([_canale(discord.TextChannel, 1)])
    ordine = []
    i = _comando(server)
    i.response.defer.side_effect = lambda **kw: ordine.append("defer")
    i.followup.send.side_effect = lambda *a, **kw: ordine.append("followup")
    await cog.blocco_attiva.callback(cog, i, "prova")
    assert ordine == ["defer", "followup"]
    assert "Blocco totale attivo" in i.followup.send.await_args.args[0]
    i.channel.send.assert_awaited()  # il riepilogo resta anche nel canale (15 minuti)


async def test_con_il_panico_riservato_solo_chi_ha_poteri_lo_toglie(cog):
    server = _server([_canale(discord.TextChannel, 1)])
    await servizio.attiva(server, tipo=logica.TIPO_PANICO, avviato_da=1, motivo="x")
    estraneo = _comando(server, user_id=7)
    await cog.blocco_togli.callback(cog, estraneo)
    assert await lockdown_repo.get_stato(GUILD_ID) is not None
    await cog.panico_togli.callback(cog, _comando(server, user_id=PROPRIETARIO))
    assert await lockdown_repo.get_stato(GUILD_ID) is None


async def test_configura_tiene_i_tetti_e_solo_il_proprietario_la_cambia(cog):
    server = _server([])
    non_proprietario = _comando(server, user_id=7)
    await cog.panico_configura.callback(cog, non_proprietario, None, None, None, None, 5, None, None)
    assert (await lockdown_repo.get_config(GUILD_ID)).sblocco_auto_minuti == 0

    for numero in range(logica.MAX_RUOLI_AVVISO):
        await cog.panico_configura.callback(
            cog, _comando(server), fake_role(role_id=500 + numero), None, None, None, None, None, None
        )
    i = _comando(server)
    await cog.panico_configura.callback(cog, i, fake_role(role_id=999), None, None, None, None, None, None)
    assert len((await lockdown_repo.get_config(GUILD_ID)).ruoli_avviso) == logica.MAX_RUOLI_AVVISO
    assert "Al massimo" in i.response.send_message.await_args.args[0]

    await cog.panico_configura.callback(cog, _comando(server), None, fake_role(role_id=500), None, None, 90, False, True)
    c = await lockdown_repo.get_config(GUILD_ID)
    assert 500 not in c.ruoli_avviso and c.sblocco_auto_minuti == 90 and not c.solo_proprietario and c.automatico


def test_i_parametri_hanno_i_limiti_di_discord():
    import typing
    from discord import app_commands

    cmd = cog_modulo.LockdownCog.panico_configura
    firma = typing.get_type_hints(cmd.callback, include_extras=True)
    assert "Range" in repr(firma["sblocco_minuti"])
    assert "Range" in repr(typing.get_type_hints(cog_modulo.LockdownCog.blocco_attiva.callback, include_extras=True)["motivo"])
