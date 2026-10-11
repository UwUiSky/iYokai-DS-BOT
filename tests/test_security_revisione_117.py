"""
tests/test_security_revisione_117.py
====================================
Difetti trovati da cacciatore e revisore sul ramo della sicurezza (#117):
- le impostazioni che decidono chi e' esente o quanto e' forte la difesa
  (soglie, punizione, recovery, blocco della quarantena) le cambia solo chi
  gestisce, non un amministratore qualsiasi;
- un extra owner non declassa ne' sostituisce un altro extra owner;
  la lista dei fidati ha una fonte sola;
- una punizione per attacco (un caso, un DM, un avviso);
- un solo `rilascia`, per caso, che non toglie la quarantena se ce ne sono altri;
- la quarantena che non toglie i poteri non si racconta come riuscita;
- il ruolo di quarantena si prepara all'attivazione e si azzerano i permessi
  di uno gia' esistente;
- il recupero di un attacco lento usa la finestra oraria.
"""

import asyncio
import typing
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.security.anti_nuke as modulo
import cogs.security.anti_raid as modulo_raid
import core.security_quarantine as quarantena
from core.repositories.security_repo import SecuritySettings, security_repo
from core.security_logic import (
    NUKE_CATEGORY_CHANNEL,
    AntiNukeConfig,
    AntiRaidConfig,
    TrustEntry,
    aggiungi_fiducia,
    rimuovi_fiducia,
    voci_fiducia,
)
from tests.support.discord_fakes import (
    fake_guild,
    fake_interaction,
    fake_member,
    fake_role,
    fake_text_channel,
)
from tests.test_anti_nuke_117 import PROPRIETARIO_ID, _come, _risposta, _scelta
from tests.test_anti_nuke_f1 import (  # noqa: F401  (fixture condivise)
    AUTORE_ID,
    GUILD_ID,
    _canale_cancellato,
    _interazione,
    _server,
    _voce,
    attese,
    cog,
    db_finto,
)

NIENTE = discord.Permissions.none()
ADMIN = discord.Permissions(administrator=True)
QID = 7777


def _autore_che_perde_i_ruoli(*ruoli):
    autore = fake_member(user_id=AUTORE_ID, roles=list(ruoli))

    async def _edit(roles, reason=None):
        autore.roles = list(roles)

    autore.edit = AsyncMock(side_effect=_edit)
    return autore


# ====================================================================
# 1. Solo chi gestisce
# ====================================================================
@pytest.mark.parametrize("quale", ["limits", "punish", "recovery"])
async def test_un_admin_non_fidato_non_cambia_soglie_punizione_recovery(cog, quale):
    prima = await security_repo.get_settings(GUILD_ID)
    interazione = _come(999)
    if quale == "limits":
        await cog.limits.callback(cog, interazione, _scelta(NUKE_CATEGORY_CHANNEL), 1000, 3600, 0)
    elif quale == "punish":
        await cog.punish_action.callback(cog, interazione, _scelta("ban"))
    else:
        await cog.recovery.callback(cog, interazione, False)
    assert "Solo il proprietario" in _risposta(interazione)
    assert await security_repo.get_settings(GUILD_ID) == prima


async def test_un_extra_owner_puo_cambiare_soglie_e_recovery(cog):
    await cog.trusted_add.callback(cog, _come(PROPRIETARIO_ID), "888", None, _scelta("extra_owner"))
    await cog.limits.callback(cog, _come(888), _scelta(NUKE_CATEGORY_CHANNEL), 7, 30, None)
    await cog.recovery.callback(cog, _come(888), False)
    n = (await security_repo.get_settings(GUILD_ID)).anti_nuke
    assert (n.channel_max, n.channel_window_seconds, n.recovery_enabled) == (7, 30, False)


async def test_blocco_della_quarantena_e_rilascio_col_blocco_solo_a_chi_gestisce(cog, server_raid):
    raid, server = server_raid
    prima = await security_repo.get_settings(GUILD_ID)
    non_owner = _interazione_raid(server, 999)
    await raid.quarantine_hold.callback(raid, non_owner, True)
    assert "Solo il proprietario" in _risposta(non_owner)
    assert await security_repo.get_settings(GUILD_ID) == prima

    # Col blocco acceso rilasciare e' roba di chi gestisce; spento, basta il gruppo /security.
    quarantined = fake_role(role_id=QID, name="Quarantined")
    server.get_role.side_effect = lambda rid: quarantined if rid == QID else None
    await security_repo.save_settings(
        modulo_raid._replace(prima, quarantine_role_id=QID, quarantine_hold=True)
    )
    membro = fake_member(user_id=31, roles=[quarantined])
    membro.guild = server
    rifiuto = _interazione_raid(server, 999)
    await raid.rilascia.callback(raid, rifiuto, membro)
    assert "Solo il proprietario" in _risposta(rifiuto)
    membro.remove_roles.assert_not_awaited()

    await security_repo.save_settings(
        modulo_raid._replace(await security_repo.get_settings(GUILD_ID), quarantine_hold=False)
    )
    libero = _interazione_raid(server, 999)
    await raid.rilascia.callback(raid, libero, membro)
    membro.remove_roles.assert_awaited_once()


@pytest.fixture
async def server_raid(db_finto):
    """Un AntiRaidCog con un server finto che sa creare ruoli."""
    from unittest.mock import create_autospec

    from discord.ext import commands

    server = fake_guild(guild_id=GUILD_ID, owner_id=PROPRIETARIO_ID)
    server.owner = fake_member(user_id=PROPRIETARIO_ID)
    server.channels = []
    raid = modulo_raid.AntiRaidCog(create_autospec(commands.Bot, instance=True))
    return raid, server


def _interazione_raid(server, utente_id):
    return fake_interaction(guild=server, user=fake_member(user_id=utente_id))


# ====================================================================
# 2. Fiducia: un solo elenco, un extra owner non ne tocca un altro
# ====================================================================
async def test_extra_owner_non_declassa_ne_sostituisce_un_altro_extra_owner(cog):
    for uid in ("777", "888"):
        await cog.trusted_add.callback(cog, _come(PROPRIETARIO_ID), uid, None, _scelta("extra_owner"))
    for tentativo in (
        (_scelta("user"), _scelta("trusted")),      # declassa
        (_scelta("user"), _scelta("trusted"), _scelta("channel")),  # sostituisce con una fiducia limitata
    ):
        interazione = _come(777)
        await cog.trusted_add.callback(cog, interazione, "888", *tentativo)
        assert "Solo il proprietario" in _risposta(interazione)
    n = (await security_repo.get_settings(GUILD_ID)).anti_nuke
    assert {v.target_id for v in voci_fiducia(n) if v.level == "extra_owner"} == {777, 888}


def test_aggiungi_fiducia_regole_nel_core():
    base = AntiNukeConfig()
    # Il proprietario nomina; un non-proprietario no.
    con_extra, errore = aggiungi_fiducia(
        base, chi_id=1, owner_id=1, target_id=5, level="extra_owner"
    )
    assert errore is None
    _, errore = aggiungi_fiducia(con_extra, chi_id=5, owner_id=1, target_id=6, level="extra_owner")
    assert "proprietario" in errore
    # Un extra owner non cambia un altro extra owner, il proprietario si'.
    con_due, _ = aggiungi_fiducia(con_extra, chi_id=1, owner_id=1, target_id=6, level="extra_owner")
    nuova, errore = aggiungi_fiducia(con_due, chi_id=5, owner_id=1, target_id=6)
    assert nuova is None and "proprietario" in errore
    nuova, errore = aggiungi_fiducia(con_due, chi_id=1, owner_id=1, target_id=6)
    assert errore is None and not any(v.target_id == 6 and v.level == "extra_owner" for v in nuova.trust_entries)
    # Un webhook con lo stesso ID di un extra owner non c'entra.
    ok, errore = aggiungi_fiducia(con_due, chi_id=5, owner_id=1, target_id=6, kind="webhook")
    assert errore is None


def test_la_lista_dei_fidati_ha_una_fonte_sola():
    vecchio = AntiNukeConfig(trusted_ids=(10, 11), trust_entries=(TrustEntry(target_id=11, categories=("role",)),))
    assert {(v.target_id, v.categories) for v in voci_fiducia(vecchio)} == {(10, ()), (11, ("role",))}
    nuova, _ = aggiungi_fiducia(vecchio, chi_id=1, owner_id=1, target_id=12)
    assert nuova.trusted_ids == ()
    assert {v.target_id for v in nuova.trust_entries} == {10, 11, 12}
    senza, _ = rimuovi_fiducia(nuova, chi_id=1, owner_id=1, target_id=10)
    assert {v.target_id for v in senza.trust_entries} == {11, 12}
    # Togliere un ID che stava ancora in trusted_ids lo toglie davvero.
    tolto, _ = rimuovi_fiducia(vecchio, chi_id=1, owner_id=1, target_id=10)
    assert 10 not in {v.target_id for v in voci_fiducia(tolto)}


def test_limiti_di_limits_e_trusted_add_sono_rifiutati_da_discord():
    def _limiti(comando, nome):
        tipo = typing.get_type_hints(comando.callback, include_extras=True)[nome]
        range_ = next(
            (t for t in (tipo, *typing.get_args(tipo)) if hasattr(t, "_min")), None
        )
        return (range_._min, range_._max)

    assert _limiti(modulo.AntiNukeCog.limits, "max_actions") == (0, 1000)
    assert _limiti(modulo.AntiNukeCog.limits, "seconds") == (1, 3600)
    assert _limiti(modulo.AntiNukeCog.limits, "max_per_hour") == (0, 10000)
    assert _limiti(modulo.AntiNukeCog.trusted_add, "user_id") == (1, 20)
    assert _limiti(modulo.AntiNukeCog.casi, "numero") == (1, 1_000_000)


# ====================================================================
# 3. Una punizione per attacco
# ====================================================================
async def _con_alert(cog_, server, monkeypatch):
    canale = fake_text_channel()
    canale.send = AsyncMock()
    server.get_channel = MagicMock(return_value=canale)
    settings = await security_repo.get_settings(GUILD_ID)
    await security_repo.save_settings(
        SecuritySettings(GUILD_ID, settings.anti_raid, settings.anti_nuke, settings.quarantine_role_id, 4000)
    )
    dm = AsyncMock(return_value=True)
    monkeypatch.setattr(modulo, "try_dm", dm)
    return canale, dm


async def test_un_attacco_un_caso_un_dm_un_avviso(cog, monkeypatch):
    autore = _autore_che_perde_i_ruoli(fake_role(role_id=50, name="Admin", position=3))
    server = _server(autore, [[]])
    canale, dm = await _con_alert(cog, server, monkeypatch)
    settings = await security_repo.get_settings(GUILD_ID)

    for _ in range(6):  # soglia a 0: ogni evento e' gia' sopra
        await cog._handle_event(server, NUKE_CATEGORY_CHANNEL, AUTORE_ID, "cancellato #x", settings)

    casi, totale = await security_repo.list_nuke_cases(GUILD_ID)
    assert totale == 1 and casi[0].removed_role_ids == (50,)
    assert dm.await_count == 1
    assert canale.send.await_count == 1
    autore.edit.assert_awaited_once()


async def test_eventi_insieme_dello_stesso_attacco_puniscono_una_volta(cog, monkeypatch):
    autore = _autore_che_perde_i_ruoli(fake_role(role_id=50, name="Admin", position=3))
    server = _server(autore, [[]])
    await _con_alert(cog, server, monkeypatch)
    settings = await security_repo.get_settings(GUILD_ID)

    await asyncio.gather(*(
        cog._handle_event(server, NUKE_CATEGORY_CHANNEL, AUTORE_ID, "x", settings) for _ in range(6)
    ))

    assert (await security_repo.list_nuke_cases(GUILD_ID))[1] == 1
    autore.edit.assert_awaited_once()


async def test_se_la_punizione_non_tiene_si_ripete_sullo_stesso_caso(cog, monkeypatch):
    primo = fake_role(role_id=50, name="Admin", position=3)
    autore = _autore_che_perde_i_ruoli(primo)
    server = _server(autore, [[]])
    canale, dm = await _con_alert(cog, server, monkeypatch)
    settings = await security_repo.get_settings(GUILD_ID)
    await cog._handle_event(server, NUKE_CATEGORY_CHANNEL, AUTORE_ID, "x", settings)

    # Qualcuno gli ridà un ruolo: l'evento dopo lo ferma di nuovo, senza un secondo caso.
    autore.roles = [fake_role(role_id=51, name="Mod", position=2)]
    await cog._handle_event(server, NUKE_CATEGORY_CHANNEL, AUTORE_ID, "x", settings)

    assert autore.edit.await_count == 2
    casi, totale = await security_repo.list_nuke_cases(GUILD_ID)
    assert totale == 1 and set(casi[0].removed_role_ids) == {50, 51}
    assert dm.await_count == 1 and canale.send.await_count == 1


async def test_dopo_il_rilascio_un_nuovo_attacco_e_un_caso_nuovo(cog, monkeypatch):
    autore = _autore_che_perde_i_ruoli(fake_role(role_id=50, name="Admin", position=3))
    server = _server(autore, [[]])
    await _con_alert(cog, server, monkeypatch)
    settings = await security_repo.get_settings(GUILD_ID)
    await cog._handle_event(server, NUKE_CATEGORY_CHANNEL, AUTORE_ID, "x", settings)
    await security_repo.mark_nuke_case_released(GUILD_ID, 1)
    autore.roles = [fake_role(role_id=50, name="Admin", position=3)]

    await cog._handle_event(server, NUKE_CATEGORY_CHANNEL, AUTORE_ID, "x", settings)

    assert (await security_repo.list_nuke_cases(GUILD_ID))[1] == 2


async def test_il_proprietario_non_viene_contato_ne_punito(cog, monkeypatch):
    proprietario = _autore_che_perde_i_ruoli(fake_role(role_id=50, name="Admin", position=3))
    proprietario.id = 1
    server = _server(proprietario, [[]])
    server.owner_id = 1
    server.get_member.side_effect = lambda uid: proprietario if uid == 1 else None
    settings = await security_repo.get_settings(GUILD_ID)

    for _ in range(4):
        assert await cog._handle_event(server, NUKE_CATEGORY_CHANNEL, 1, "x", settings) is None

    proprietario.edit.assert_not_awaited()
    assert (await security_repo.list_nuke_cases(GUILD_ID))[1] == 0


# ====================================================================
# 4. Un solo rilascia, per caso
# ====================================================================
def _server_per_rilascio(autore, ruoli):
    server = fake_guild(guild_id=GUILD_ID, owner_id=PROPRIETARIO_ID)
    server.get_role = MagicMock(side_effect=lambda rid: ruoli.get(rid))
    server.me.top_role = fake_role(role_id=9, position=10)
    autore.guild = server
    server.get_member.side_effect = lambda uid: autore if uid == autore.id else None
    return server


async def test_rilasciare_un_caso_non_toglie_la_quarantena_se_ce_n_e_un_altro(clean_db, monkeypatch):
    monkeypatch.setattr(security_repo, "_pool_provider", lambda: clean_db)
    quarantined = fake_role(role_id=QID, name="Quarantined", position=1)
    r52, r53 = fake_role(role_id=52, name="A", position=2), fake_role(role_id=53, name="B", position=3)
    autore = _autore_che_perde_i_ruoli(quarantined)
    server = _server_per_rilascio(autore, {QID: quarantined, 52: r52, 53: r53})
    await security_repo.save_settings(
        SecuritySettings(GUILD_ID, AntiRaidConfig(), AntiNukeConfig(), QID, None)
    )
    primo = await security_repo.create_nuke_case(GUILD_ID, AUTORE_ID, "channel", "a", "q", (52,))
    secondo = await security_repo.create_nuke_case(GUILD_ID, AUTORE_ID, "role", "b", "q", (53,))

    esito = await quarantena.rilascia_utente(autore, caso_numero=primo, reason="r")

    assert esito.riuscito and esito.quarantena_tenuta and esito.altri_casi == (secondo,)
    ruoli_ora = [r.id for r in autore.roles]
    assert 52 in ruoli_ora and QID in ruoli_ora and 53 not in ruoli_ora  # solo i ruoli DI QUEL caso
    assert (await security_repo.get_nuke_case(GUILD_ID, primo)).released_at is not None
    assert (await security_repo.get_nuke_case(GUILD_ID, secondo)).released_at is None

    esito = await quarantena.rilascia_utente(autore, caso_numero=secondo, reason="r")
    assert not esito.quarantena_tenuta
    assert sorted(r.id for r in autore.roles) == [52, 53]  # quarantena tolta, ruoli di entrambi


async def test_rilascio_non_rimette_ruoli_cancellati_gestiti_o_sopra_al_bot(clean_db, monkeypatch):
    monkeypatch.setattr(security_repo, "_pool_provider", lambda: clean_db)
    gestito = fake_role(role_id=60, name="Booster", position=2, managed=True)
    alto = fake_role(role_id=61, name="Alto", position=50)
    buono = fake_role(role_id=62, name="Buono", position=3)
    autore = _autore_che_perde_i_ruoli()
    _server_per_rilascio(autore, {60: gestito, 61: alto, 62: buono})
    numero = await security_repo.create_nuke_case(GUILD_ID, AUTORE_ID, "channel", "a", "q", (60, 61, 62, 63))

    esito = await quarantena.rilascia_utente(autore, caso_numero=numero, reason="r")

    assert esito.riuscito and sorted(esito.saltati) == [60, 61, 63]
    assert [r.id for r in autore.roles] == [62]


async def test_rilascio_fallito_non_segna_il_caso_rilasciato(clean_db, monkeypatch):
    monkeypatch.setattr(security_repo, "_pool_provider", lambda: clean_db)
    buono = fake_role(role_id=62, name="Buono", position=3)
    autore = fake_member(user_id=AUTORE_ID, roles=[])
    autore.edit = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=403), "no"))
    _server_per_rilascio(autore, {62: buono})
    numero = await security_repo.create_nuke_case(GUILD_ID, AUTORE_ID, "channel", "a", "q", (62,))

    esito = await quarantena.rilascia_utente(autore, caso_numero=numero, reason="r")

    assert not esito.riuscito
    assert (await security_repo.get_nuke_case(GUILD_ID, numero)).released_at is None


async def test_dopo_il_rilascio_i_contatori_dell_utente_ripartono(cog):
    import cogs.security.anti_nuke as nuke

    ora = discord.utils.utcnow()
    for _ in range(5):
        nuke.security_rate_tracker.record_and_count(GUILD_ID, AUTORE_ID, NUKE_CATEGORY_CHANNEL, ora, 60)
        nuke.security_rate_tracker.record_and_count(GUILD_ID, AUTORE_ID, f"{NUKE_CATEGORY_CHANNEL}:ora", ora, 3600)
    numero = await security_repo.create_nuke_case(GUILD_ID, AUTORE_ID, "channel", "a", "q", ())
    autore = _autore_che_perde_i_ruoli()
    interazione = _interazione()
    interazione.guild.get_member = MagicMock(return_value=autore)
    interazione.guild.get_role = MagicMock(return_value=None)

    await cog.rilascia.callback(cog, interazione, numero)

    assert nuke.security_rate_tracker.record_and_count(GUILD_ID, AUTORE_ID, NUKE_CATEGORY_CHANNEL, ora, 60) == 1
    assert nuke.security_rate_tracker.record_and_count(GUILD_ID, AUTORE_ID, f"{NUKE_CATEGORY_CHANNEL}:ora", ora, 3600) == 1


async def test_antiraid_rilascia_non_toglie_la_quarantena_a_chi_ha_un_caso_nuke_attivo(server_raid):
    raid, server = server_raid
    quarantined = fake_role(role_id=QID, name="Quarantined", position=1)
    server.get_role.side_effect = lambda rid: quarantined if rid == QID else None
    await security_repo.save_settings(
        modulo_raid._replace(await security_repo.get_settings(GUILD_ID), quarantine_role_id=QID)
    )
    membro = fake_member(user_id=AUTORE_ID, roles=[quarantined])
    membro.guild = server
    await security_repo.create_nuke_case(GUILD_ID, AUTORE_ID, "channel", "a", "q", (52,))

    interazione = _interazione_raid(server, PROPRIETARIO_ID)
    await raid.rilascia.callback(raid, interazione, membro)

    membro.remove_roles.assert_not_awaited()
    assert "casi anti-nuke attivi" in interazione.followup.send.call_args.args[0]


# ====================================================================
# 5. Quarantena fail-open
# ====================================================================
def _http_403():
    return discord.Forbidden(MagicMock(status=403, reason="Forbidden"), "no")


async def test_quarantena_senza_ruoli_tolti_non_e_riuscita(monkeypatch):
    q = fake_role(role_id=QID, name="Quarantined", position=1)
    alto = fake_role(role_id=77, name="Admin", position=50, permissions=ADMIN)
    membro = fake_member(user_id=AUTORE_ID, roles=[alto])
    membro.guild = fake_guild(guild_id=GUILD_ID)
    membro.edit = AsyncMock(side_effect=_http_403())
    membro.add_roles = AsyncMock()
    monkeypatch.setattr(quarantena, "ruolo_quarantena", AsyncMock(return_value=q))

    esito = await quarantena.metti_in_quarantena(membro, "x", togli_ruoli=True)

    assert esito.in_quarantena and esito.ruoli_non_tolti and not esito.completo and esito.ruoli_tolti == []
    membro.add_roles.assert_awaited_once()  # il ripiego: almeno il ruolo di quarantena


async def test_quarantena_senza_neanche_il_ruolo_non_e_riuscita(monkeypatch):
    q = fake_role(role_id=QID, name="Quarantined", position=1)
    membro = fake_member(user_id=AUTORE_ID, roles=[])
    membro.guild = fake_guild(guild_id=GUILD_ID)
    membro.edit = AsyncMock(side_effect=_http_403())
    membro.add_roles = AsyncMock(side_effect=_http_403())
    monkeypatch.setattr(quarantena, "ruolo_quarantena", AsyncMock(return_value=q))

    esito = await quarantena.metti_in_quarantena(membro, "x", togli_ruoli=True)

    assert not esito.in_quarantena and not esito.completo


async def test_l_avviso_dice_che_i_ruoli_non_sono_stati_tolti(cog, monkeypatch):
    await cog.punish_action.callback(cog, _interazione(), _scelta("quarantine"))
    q = fake_role(role_id=QID, name="Quarantined", position=1)
    alto = fake_role(role_id=77, name="Admin", position=50, permissions=ADMIN)
    autore = fake_member(user_id=AUTORE_ID, roles=[alto])
    autore.edit = AsyncMock(side_effect=_http_403())
    autore.add_roles = AsyncMock()
    server = _server(autore, [[]])
    monkeypatch.setattr(quarantena, "ruolo_quarantena", AsyncMock(return_value=q))
    monkeypatch.setattr(modulo, "metti_in_quarantena", quarantena.metti_in_quarantena)

    esito, tolti = await modulo._punish_actor(server, AUTORE_ID, AntiNukeConfig(punish_action="quarantine"), "r")

    assert "NON" in esito and "ancora potente" in esito and tolti == []
    assert "messo in quarantena" not in esito  # non si dichiara una cosa che non e' successa


async def test_il_caso_registra_l_esito_parziale(cog, monkeypatch):
    await cog.punish_action.callback(cog, _interazione(), _scelta("quarantine"))
    monkeypatch.setattr(
        modulo, "metti_in_quarantena",
        AsyncMock(return_value=quarantena.EsitoQuarantena(True, [], ruoli_non_tolti=True)),
    )
    autore = fake_member(user_id=AUTORE_ID, roles=[fake_role(role_id=52, position=5)])
    server = _server(autore, [[]])

    await cog._handle_event(server, NUKE_CATEGORY_CHANNEL, AUTORE_ID, "azione")

    assert "NON sono stati tolti" in (await security_repo.get_nuke_case(GUILD_ID, 1)).punishment


# ---- il ruolo si prepara all'attivazione, non durante l'attacco
async def test_antinuke_enable_prepara_il_ruolo_di_quarantena(cog, monkeypatch):
    preparato = AsyncMock(return_value=fake_role(role_id=QID, name="Quarantined", position=1))
    monkeypatch.setattr(modulo, "ruolo_quarantena", preparato)
    monkeypatch.setattr(modulo, "problemi_ruoli_del_bot", lambda *_: ())
    await cog.punish_action.callback(cog, _interazione(), _scelta("quarantine"))
    preparato.reset_mock()

    interazione = _interazione()
    await cog.enable.callback(cog, interazione, True)

    preparato.assert_awaited_once_with(interazione.guild)
    interazione.followup.send.assert_not_awaited()  # tutto a posto: niente avviso


async def test_antinuke_enable_avvisa_se_il_ruolo_non_si_puo_creare(cog, monkeypatch):
    monkeypatch.setattr(modulo, "ruolo_quarantena", AsyncMock(return_value=None))
    await cog.punish_action.callback(cog, _interazione(), _scelta("quarantine"))
    interazione = _interazione()
    await cog.enable.callback(cog, interazione, True)
    assert "ruolo di quarantena" in interazione.followup.send.call_args.args[0]


async def test_antiraid_enable_crea_il_ruolo_subito(server_raid):
    raid, server = server_raid
    ruoli = {}

    async def _crea(**kw):
        ruolo = fake_role(role_id=5000, name=kw["name"])
        ruoli[5000] = ruolo
        server.roles = list(ruoli.values())
        return ruolo

    server.create_role.side_effect = _crea
    server.get_role.side_effect = ruoli.get
    interazione = _interazione_raid(server, PROPRIETARIO_ID)

    await raid.enable.callback(raid, interazione, True)

    server.create_role.assert_awaited_once()
    assert (await security_repo.get_settings(GUILD_ID)).quarantine_role_id == 5000


async def test_ruolo_quarantined_fatto_a_mano_perde_i_permessi(server_raid):
    _, server = server_raid
    a_mano = fake_role(role_id=321, name="Quarantined", permissions=ADMIN)
    a_mano.edit = AsyncMock()
    server.roles = [a_mano]

    ruolo = await quarantena.ruolo_quarantena(server)

    assert ruolo is a_mano
    assert a_mano.edit.call_args.kwargs["permissions"] == NIENTE


def test_problemi_del_ruolo_di_quarantena_sopra_al_bot():
    bot = fake_role(role_id=2, name="Bot", position=3)
    sopra = fake_role(role_id=QID, name="Quarantined", position=5)
    server = fake_guild()
    server.me.top_role, server.me.roles = bot, [bot]
    server.me.guild_permissions = ADMIN
    server.roles = [bot, sopra]
    server.get_role = MagicMock(return_value=sopra)
    problemi = quarantena.problemi_ruoli_del_bot(server, QID)
    assert any("ruolo di quarantena sta sopra" in p for p in problemi)


async def test_status_antiraid_mostra_gli_avvisi(server_raid):
    raid, server = server_raid
    server.me.guild_permissions = NIENTE
    server.me.top_role = fake_role(role_id=2, name="Bot", position=3)
    server.me.roles = [server.me.top_role]
    server.roles = [server.me.top_role]
    interazione = _interazione_raid(server, PROPRIETARIO_ID)
    await raid.status.callback(raid, interazione)
    assert "⚠️" in _risposta(interazione) and "Gestisci ruoli" in _risposta(interazione)


# ====================================================================
# 8. Recupero con la finestra oraria
# ====================================================================
async def test_attacco_lento_si_recupera_per_intero(cog, monkeypatch):
    await cog.limits.callback(cog, _interazione(), _scelta(NUKE_CATEGORY_CHANNEL), 100, 60, 2)
    ora = [discord.utils.utcnow()]
    monkeypatch.setattr(discord.utils, "utcnow", lambda: ora[0])
    autore = _autore_che_perde_i_ruoli()
    voci = [_voce(discord.AuditLogAction.channel_delete, AUTORE_ID, 7001 + n) for n in range(3)]
    server = _server(autore, [voci])
    canali = []
    for n in range(3):
        canale = _canale_cancellato(fake_text_channel(), server, f"c{n}")
        canale.id = 7001 + n
        canale.topic, canale.nsfw, canale.slowmode_delay = None, False, 0
        canale.is_news.return_value = False
        canali.append(canale)

    for canale in canali:  # una ogni 10 minuti: ognuna fuori dalla finestra di 60s dell'altra
        voci_ora = voci
        for v in voci_ora:
            v.created_at = ora[0]
        await cog.on_guild_channel_delete(canale)
        ora[0] = ora[0] + timedelta(minutes=10)

    nomi = sorted(c.kwargs["name"] for c in server.create_text_channel.await_args_list)
    assert nomi == ["c0", "c1", "c2"]
