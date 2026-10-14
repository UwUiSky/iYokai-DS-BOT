"""
tests/test_anti_raid_r6.py
==========================
Catalogo #117, anti-raid: filtri all'ingresso con azione propria (SIC-023,
024, 026, 027, 028), soglia sui soli sospetti (SIC-029), account creati
vicini e nomi simili (SIC-030/031), kick e ban al raid (SIC-032), azione su
chi è entrato prima (SIC-033), ping dei ruoli (SIC-034), elenco (SIC-035),
segnale di rete (SIC-037), segnalazione a chi gestisce il bot (SIC-038).
"""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands

import cogs.security.anti_raid as modulo
from core import security_raid_state
from core.repositories.security_repo import _from_json, _to_json, security_repo
from core.security_join_logic import (
    Ingresso,
    account_vicini,
    azione_piu_forte,
    azzera_ingressi,
    ingresso_in_rete,
    nome_pubblicitario,
    nome_vietato,
    nomi_simili,
)
from tests.support.discord_fakes import fake_role, fake_text_channel
from tests.test_anti_raid_f1 import (  # noqa: F401  (fixture condivise)
    GUILD_ID,
    INIZIO,
    _azione,
    _ingresso,
    _interazione,
    cog,
    db_finto,
    orologio,
    server,
)


@pytest.fixture(autouse=True)
def _memoria_pulita(monkeypatch):
    azzera_ingressi()
    security_raid_state._ultimo_ingresso.clear()
    monkeypatch.setattr(modulo, "PAUSA_AZIONI_SECONDI", 0)
    yield
    azzera_ingressi()
    security_raid_state._ultimo_ingresso.clear()


def _scelta(valore):
    return app_commands.Choice(name=valore, value=valore)


async def _filtro(cog, filtro, azione, messaggio=None):
    await cog.filtro_ingresso.callback(cog, _interazione(), _scelta(filtro), _scelta(azione), messaggio)


async def _categorie():
    return [r["category"] for r in await security_repo.get_recent_actions(GUILD_ID)]


# ------------------------------------------------------------------ logica pura
def test_nomi_pubblicitari_e_vietati():
    assert nome_pubblicitario(("Entra in discord.gg/abc", None))
    assert nome_pubblicitario(("x", "discord . gg / spam"))
    assert not nome_pubblicitario(("Mario", "mario"))
    assert nome_vietato(("FreeNitroBot",), ("*free*nitro*",)) == "*free*nitro*"
    assert nome_vietato(("Il_Truffatore",), ("truff",)) == "truff"
    assert nome_vietato(("Mario",), ("*free*", "truff")) is None


def test_segnali_sugli_ultimi_ingressi():
    def ing(i, nome, minuti):
        return Ingresso(i, nome, INIZIO - timedelta(days=30, minutes=minuti), INIZIO)

    recenti = [ing(1, "raider01", 0), ing(2, "raider02", 3), ing(3, "Giulia", 600)]
    assert account_vicini(recenti, INIZIO - timedelta(days=30, minutes=1), 300) == 2
    assert nomi_simili(recenti, "raider03") == 2
    assert nomi_simili(recenti, "zz") == 0
    assert azione_piu_forte(["timeout", "ban", "quarantena"]) == "ban"


def test_segnale_di_rete_conta_i_server_diversi_nella_finestra():
    assert [ingresso_in_rete(7, g, INIZIO) for g in (1, 1, 2, 3, 4)] == [1, 0, 2, 3, 4]
    assert ingresso_in_rete(7, 5, INIZIO + timedelta(hours=1)) == 1


def test_le_nuove_scelte_sopravvivono_al_salvataggio():
    from core.repositories.security_repo import _default_settings

    base = _default_settings(1)
    nuove = modulo._replace(
        base, azione_eta="kick", nomi_vietati=("a*",), ruoli_ping=(5,), retroattivo=True,
        account_vicini_minimo=3, conta_solo_sospetti=True, messaggio_eta="ciao",
    )
    letto = _from_json(1, _to_json(nuove)).anti_raid
    assert (letto.azione_eta, letto.nomi_vietati, letto.ruoli_ping, letto.retroattivo) == ("kick", ("a*",), (5,), True)
    assert letto.account_vicini_minimo == 3 and letto.conta_solo_sospetti and letto.messaggio_eta == "ciao"


# ------------------------------------------------------------ filtri all'ingresso
async def test_account_giovane_riceve_il_dm_prima_del_kick(cog, server):
    await _filtro(cog, "eta", "kick", "Servono 3 giorni di account.")
    ordine = []
    nuovo = _ingresso(server, 50)
    nuovo.created_at = INIZIO - timedelta(hours=1)
    nuovo.send.side_effect = lambda *a, **k: ordine.append("dm")
    nuovo.kick.side_effect = lambda *a, **k: ordine.append("kick")

    await cog.on_member_join(nuovo)

    assert ordine == ["dm", "kick"]
    assert "Servono 3 giorni" in nuovo.send.call_args.kwargs["embed"].description
    assert await _categorie() == ["filtro_ingresso"]


async def test_bot_non_verificato_bannato_quello_verificato_entra(cog, server):
    await _filtro(cog, "bot_non_verificato", "ban")
    falso = _ingresso(server, 60)
    falso.bot = True
    falso.public_flags = MagicMock(verified_bot=False)
    vero = _ingresso(server, 61)
    vero.bot = True
    vero.public_flags = MagicMock(verified_bot=True)

    await cog.on_member_join(falso)
    await cog.on_member_join(vero)

    assert [c.args[0] for c in server.ban.await_args_list] == [falso]


async def test_nome_vietato_e_pubblicitario_scegliono_l_azione_piu_forte(cog, server):
    await cog.nomi_vietati.callback(cog, _interazione(), _scelta("aggiungi"), "*nitro*")
    await _filtro(cog, "nome_vietato", "timeout")
    await _filtro(cog, "nome_pubblicitario", "kick")
    solo_vietato = _ingresso(server, 70)
    solo_vietato.name = solo_vietato.display_name = "freenitro"
    solo_vietato.global_name = None
    entrambi = _ingresso(server, 71)
    entrambi.name, entrambi.global_name, entrambi.display_name = "nitro", "discord.gg/x", "nitro"

    await cog.on_member_join(solo_vietato)
    await cog.on_member_join(entrambi)

    solo_vietato.timeout.assert_awaited_once()
    solo_vietato.kick.assert_not_awaited()
    entrambi.kick.assert_awaited_once()
    entrambi.timeout.assert_not_awaited()


async def test_lista_dei_nomi_vietati_ha_un_tetto(cog, monkeypatch):
    monkeypatch.setattr(modulo, "MAX_NOMI_VIETATI", 3)
    for i in range(modulo.MAX_NOMI_VIETATI):
        await cog.nomi_vietati.callback(cog, _interazione(), _scelta("aggiungi"), f"p{i}")
    interazione = _interazione()
    await cog.nomi_vietati.callback(cog, interazione, _scelta("aggiungi"), "troppo")
    assert "piena" in interazione.response.send_message.call_args.args[0]
    settings = await security_repo.get_settings(GUILD_ID)
    assert len(settings.anti_raid.nomi_vietati) == modulo.MAX_NOMI_VIETATI


# ------------------------------------------------------------------ segnali di raid
async def test_soglia_contata_solo_sui_sospetti(cog, server):
    await cog.join_rate.callback(cog, _interazione(), 2, 60, _scelta("sospetti"))
    await _azione(cog, "kick")
    normali = [_ingresso(server, 100 + i) for i in range(4)]
    for m in normali:
        await cog.on_member_join(m)
    assert not any(m.kick.await_count for m in normali)

    sospetti = [_ingresso(server, 200 + i, avatar=False) for i in range(3)]
    for m in sospetti:
        await cog.on_member_join(m)
    sospetti[2].kick.assert_awaited_once()


async def test_account_creati_vicini_fanno_scattare_il_raid(cog, server):
    await cog.join_rate.callback(cog, _interazione(), 100, 60, None)
    await cog.segnali.callback(cog, _interazione(), 3, 10, None, None)
    await _azione(cog, "ban")
    membri = [_ingresso(server, 300 + i) for i in range(3)]
    for i, m in enumerate(membri):
        m.created_at = INIZIO - timedelta(days=50, minutes=i)
    for m in membri:
        await cog.on_member_join(m)
    assert [c.args[0] for c in server.ban.await_args_list] == [membri[2]]


async def test_nomi_simili_fanno_scattare_il_raid(cog, server):
    await cog.join_rate.callback(cog, _interazione(), 100, 60, None)
    await cog.segnali.callback(cog, _interazione(), None, None, 3, None)
    await _azione(cog, "kick")
    membri = [_ingresso(server, 400 + i) for i in range(3)]
    for i, m in enumerate(membri):
        m.name = f"spammer{i}"
        m.created_at = INIZIO - timedelta(days=100 * (i + 1))
    for m in membri:
        await cog.on_member_join(m)
    membri[2].kick.assert_awaited_once()
    membri[0].kick.assert_not_awaited()


async def test_ban_al_raid_anche_su_chi_e_entrato_prima(cog, server):
    await cog.segnali.callback(cog, _interazione(), None, None, None, True)
    await _azione(cog, "ban")
    membri = [_ingresso(server, 500 + i) for i in range(4)]
    server.get_member.side_effect = {m.id: m for m in membri}.get
    for m in membri:
        await cog.on_member_join(m)
    bannati = [c.args[0] for c in server.ban.await_args_list]
    # Il terzo fa scattare il raid, poi tocca ai due entrati prima, poi al quarto.
    assert bannati == [membri[2], membri[0], membri[1], membri[3]]
    assert (await _categorie()).count("raid_join") == 4


async def test_azione_su_chi_e_entrato_prima_salta_i_non_sospetti(cog, server):
    # Soglia contata solo sui sospetti: i membri normali entrati nella finestra non si toccano.
    await cog.join_rate.callback(cog, _interazione(), 2, 60, _scelta("sospetti"))
    await cog.segnali.callback(cog, _interazione(), None, None, None, True)
    await _azione(cog, "kick")
    normali = [_ingresso(server, 600 + i) for i in range(2)]
    sospetti = [_ingresso(server, 700 + i, avatar=False) for i in range(3)]
    server.get_member.side_effect = {m.id: m for m in normali + sospetti}.get
    for m in normali + sospetti:
        await cog.on_member_join(m)
    assert all(m.kick.await_count == 1 for m in sospetti)
    assert not any(m.kick.await_count for m in normali)


async def test_primo_allarme_pinga_i_ruoli_gli_aggiornamenti_no(cog, server):
    canale = fake_text_channel(channel_id=88)
    canale.send.return_value = MagicMock(edit=AsyncMock())
    server.get_channel.side_effect = {88: canale}.get
    await cog.alert_channel.callback(cog, _interazione(), canale)
    await cog.ping_ruoli.callback(cog, _interazione(), fake_role(role_id=11), fake_role(role_id=12), None)
    await _azione(cog, "verification")

    for i in range(4):
        await cog.on_member_join(_ingresso(server, 600 + i))

    canale.send.assert_awaited_once()
    assert canale.send.call_args.kwargs["content"] == "<@&11> <@&12>"
    assert canale.send.call_args.kwargs["allowed_mentions"].roles is True


async def test_elenco_manda_il_file_con_tutti_gli_account(cog, server):
    await _azione(cog, "verification")
    for i in range(5):
        await cog.on_member_join(_ingresso(server, 700 + i))
    interazione = _interazione()
    interazione.response.is_done.return_value = False
    await cog.elenco.callback(cog, interazione, 24)
    file = interazione.response.send_message.call_args.kwargs["file"]
    righe = file.fp.read().decode().splitlines()
    assert [r.split("\t")[0] for r in righe] == ["702", "703", "704"]


async def test_segnala_manda_gli_ultimi_ingressi_a_chi_gestisce_il_bot(cog, server):
    for i in range(2):
        await cog.on_member_join(_ingresso(server, 800 + i))
    gestore = MagicMock(send=AsyncMock())
    cog.bot.fetch_user = AsyncMock(return_value=gestore)
    interazione = _interazione()
    await cog.segnala.callback(cog, interazione, "raid lento")
    testo = gestore.send.call_args.args[0]
    assert "raid lento" in testo and "2 ingressi" in testo
    assert "raid_segnalato" in await _categorie()


async def test_segnale_di_rete_avvisa_lo_staff_una_volta(cog, server):
    canale = fake_text_channel(channel_id=89)
    server.get_channel.side_effect = {89: canale}.get
    await cog.alert_channel.callback(cog, _interazione(), canale)
    for g in range(1, modulo.SERVER_RETE_MINIMI):
        ingresso_in_rete(900, 10_000 + g, INIZIO)
    membro = _ingresso(server, 900)
    await cog.on_member_join(membro)
    await cog.on_member_join(membro)
    titoli = [c.kwargs["embed"].title for c in canale.send.await_args_list]
    assert titoli.count("🌐 Anti-Raid — ingresso in molti server") == 1
