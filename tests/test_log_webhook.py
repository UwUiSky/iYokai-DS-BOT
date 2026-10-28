"""
tests/test_log_webhook.py
=========================
Log via webhook (#113, D33): raggruppamento, ripiego sul canale, archivio del token cifrato, comando.
Il webhook è un finto con la firma vera (autospec); il database è vero.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, create_autospec, patch

import discord
import pytest

import core.log_webhook as lw
from core.oauth_crypto import generate_key
from core.repositories.log_webhook_repo import LogWebhookRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_text_channel


def _canale(guild_id=10, canale_id=20):
    canale = fake_text_channel(canale_id)
    canale.guild = fake_guild(guild_id)
    return canale


def _webhook():
    w = create_autospec(discord.Webhook, instance=True)
    w.send = AsyncMock()
    return w


@pytest.fixture(autouse=True)
def _pulito(monkeypatch):
    lw._vivi.clear()
    lw._blocchi.clear()  # un blocco resta legato al ciclo di eventi del test che lo ha usato
    monkeypatch.setattr(lw, "ATTESA_RAGGRUPPO", 0.01)
    monkeypatch.setattr(lw.log_webhook_repo, "elimina", AsyncMock())
    yield
    lw._vivi.clear()


def _embed(testo="x"):
    return discord.Embed(description=testo)


async def test_piu_righe_ravvicinate_escono_in_un_solo_messaggio():
    web = _webhook()
    dest = lw.CanaleWebhook(_canale(), web)
    for i in range(3):
        assert await dest.send(embed=_embed(str(i))) is None
    web.send.assert_not_awaited()
    await asyncio.sleep(0.1)
    web.send.assert_awaited_once()
    assert [e.description for e in web.send.await_args.kwargs["embeds"]] == ["0", "1", "2"]


async def test_a_dieci_embed_parte_subito_e_non_oltre_dieci():
    web = _webhook()
    dest = lw.CanaleWebhook(_canale(), web)
    for i in range(25):
        await dest.send(embed=_embed(str(i)))
    assert [len(c.kwargs["embeds"]) for c in web.send.await_args_list] == [10, 10]
    await asyncio.sleep(0.1)
    assert len(web.send.await_args_list[-1].kwargs["embeds"]) == 5


async def test_il_messaggio_non_supera_i_caratteri_di_discord():
    web = _webhook()
    dest = lw.CanaleWebhook(_canale(), web)
    for _ in range(4):
        await dest.send(embed=_embed("a" * 2000))
    await asyncio.sleep(0.1)
    for chiamata in web.send.await_args_list:
        assert sum(len(e) for e in chiamata.kwargs["embeds"]) <= 6000
    assert sum(len(c.kwargs["embeds"]) for c in web.send.await_args_list) == 4


async def test_con_bottoni_scrive_il_canale_non_il_webhook():
    canale = _canale()
    web = _webhook()
    dest = lw.CanaleWebhook(canale, web)
    vista = discord.ui.View()
    await dest.send(embed=_embed(), view=vista)
    canale.send.assert_awaited_once()
    web.send.assert_not_awaited()


async def test_un_file_lo_scrive_il_canale_non_il_webhook():
    """Il webhook chiude il file anche quando fallisce: il ripiego sul canale manderebbe un file chiuso
    (ValueError, non HTTPException) e il transcript del ticket si perderebbe."""
    canale = _canale()
    web = _webhook()
    dest = lw.CanaleWebhook(canale, web)
    await dest.send(content="ciao", file=MagicMock())
    await dest.send(content="ciao", files=[MagicMock()])
    assert canale.send.await_count == 2
    web.send.assert_not_awaited()


async def test_un_testo_senza_file_passa_dal_webhook_subito():
    web = _webhook()
    dest = lw.CanaleWebhook(_canale(), web)
    await dest.send(content="ciao")
    web.send.assert_awaited_once()
    assert web.send.await_args.kwargs["wait"] is True


async def test_webhook_cancellato_i_log_tornano_al_canale_e_il_webhook_si_dimentica():
    canale = _canale()
    web = _webhook()
    web.send.side_effect = discord.NotFound(MagicMock(status=404, reason="x"), "Unknown Webhook")
    dest = lw.CanaleWebhook(canale, web)
    lw._vivi[(10, 20)] = dest
    await dest.send(embed=_embed("a"))
    await dest.send(embed=_embed("b"))
    await asyncio.sleep(0.1)
    assert canale.send.await_count == 2
    lw.log_webhook_repo.elimina.assert_awaited_once_with(10, 20)
    assert (10, 20) not in lw._vivi


async def test_avvolgi_spento_o_senza_permesso_resta_il_canale(monkeypatch):
    canale = _canale()
    assert await lw.avvolgi(canale, False) is canale
    monkeypatch.setattr(lw, "_client_di", lambda c: MagicMock())
    monkeypatch.setattr(lw.log_webhook_repo, "get", AsyncMock(return_value=None))
    canale.permissions_for.return_value = discord.Permissions.none()
    assert await lw.avvolgi(canale, True) is canale


async def test_avvolgi_crea_il_webhook_una_volta_e_lo_riusa(monkeypatch):
    canale = _canale()
    nuovo = MagicMock(id=555, token="tok")
    canale.create_webhook = AsyncMock(return_value=nuovo)
    canale.permissions_for.return_value = discord.Permissions(manage_webhooks=True)
    monkeypatch.setattr(lw, "_client_di", lambda c: MagicMock())
    monkeypatch.setattr(lw.log_webhook_repo, "get", AsyncMock(return_value=None))
    monkeypatch.setattr(lw.log_webhook_repo, "salva", AsyncMock())

    primo = await lw.avvolgi(canale, True)
    secondo = await lw.avvolgi(canale, True)

    assert isinstance(primo, lw.CanaleWebhook) and primo is secondo
    canale.create_webhook.assert_awaited_once()
    lw.log_webhook_repo.salva.assert_awaited_once_with(10, 20, 555, "tok")


async def test_righe_insieme_su_un_canale_nuovo_creano_un_solo_webhook(monkeypatch):
    """In un raid arrivano molte righe insieme: un webhook per riga riempirebbe il canale (15 al massimo)."""
    canale = _canale()

    async def crea(**kw):
        await asyncio.sleep(0)
        return MagicMock(id=555, token="tok")

    canale.create_webhook = AsyncMock(side_effect=crea)
    canale.permissions_for.return_value = discord.Permissions(manage_webhooks=True)
    monkeypatch.setattr(lw, "_client_di", lambda c: MagicMock())
    monkeypatch.setattr(lw.log_webhook_repo, "get", AsyncMock(return_value=None))
    monkeypatch.setattr(lw.log_webhook_repo, "salva", AsyncMock())

    destinazioni = await asyncio.gather(*(lw.avvolgi(canale, True) for _ in range(5)))

    canale.create_webhook.assert_awaited_once()
    assert all(d is destinazioni[0] for d in destinazioni)


async def test_senza_chiave_il_webhook_appena_creato_si_cancella(monkeypatch):
    from core.repositories.log_webhook_repo import ChiaveNonConfigurata

    canale = _canale()
    nuovo = MagicMock(id=555, token="tok")
    nuovo.delete = AsyncMock()
    canale.create_webhook = AsyncMock(return_value=nuovo)
    canale.permissions_for.return_value = discord.Permissions(manage_webhooks=True)
    monkeypatch.setattr(lw, "_client_di", lambda c: MagicMock())
    monkeypatch.setattr(lw.log_webhook_repo, "get", AsyncMock(return_value=None))
    monkeypatch.setattr(lw.log_webhook_repo, "salva", AsyncMock(side_effect=ChiaveNonConfigurata()))
    assert await lw.avvolgi(canale, True) is canale
    nuovo.delete.assert_awaited_once()


async def test_il_router_scrive_dal_webhook_e_conta_come_inviato():
    import core.channel_router as router

    web = _webhook()
    dest = lw.CanaleWebhook(_canale(), web)
    assert await router.invia_a(dest, fake_guild(10), "eventi", embed=_embed("evento")) is True
    await asyncio.sleep(0.1)
    web.send.assert_awaited_once()


# ---------------------------------------------------------------- archivio
@pytest.fixture
def repo(clean_db):
    return LogWebhookRepository(lambda: clean_db, lambda: CHIAVE), clean_db


CHIAVE = generate_key()


async def test_il_token_si_salva_cifrato_e_si_rilegge(repo):
    r, pool = repo
    await r.salva(10, 20, 555, "token-segreto")
    grezzo = await pool.fetchval("SELECT encrypted_token FROM log_webhooks WHERE guild_id = 10")
    assert "token-segreto" not in grezzo
    assert await r.get(10, 20) == (555, "token-segreto")
    assert await r.get(10, 21) is None


async def test_il_token_non_si_legge_con_un_altro_canale_o_un_altra_chiave(repo):
    r, pool = repo
    await r.salva(10, 20, 555, "tok")
    await pool.execute("UPDATE log_webhooks SET channel_id = 21 WHERE channel_id = 20")  # riga spostata
    assert await r.get(10, 21) is None  # il dato associato non torna
    altro = LogWebhookRepository(lambda: pool, lambda: generate_key())
    await r.salva(10, 22, 556, "tok2")
    assert await altro.get(10, 22) is None


async def test_spegnere_toglie_le_righe_e_da_il_token_per_cancellare(repo):
    r, pool = repo
    await r.salva(10, 20, 555, "tok")
    await r.salva(11, 20, 556, "altro-server")
    assert await r.elimina_server(10) == [(20, 555, "tok")]
    assert await pool.fetchval("SELECT count(*) FROM log_webhooks") == 1


async def test_senza_chiave_non_si_salva(repo):
    from core.repositories.log_webhook_repo import ChiaveNonConfigurata

    _, pool = repo
    senza = LogWebhookRepository(lambda: pool, lambda: "")
    assert senza.chiave_presente() is False
    with pytest.raises(ChiaveNonConfigurata):
        await senza.salva(10, 20, 555, "tok")


# ---------------------------------------------------------------- comando
async def _cog():
    from cogs.utility.log_webhook import LogWebhookCog

    return LogWebhookCog(MagicMock())


async def test_comando_accende_solo_con_chiave_e_permesso():
    import cogs.utility.log_webhook as modulo

    cog = await _cog()
    server = fake_guild(10)
    server.me.guild_permissions = discord.Permissions(manage_webhooks=True)
    i = fake_interaction(guild=server, user=fake_member(user_id=1))
    with patch.object(modulo.log_webhook_repo, "chiave_presente", return_value=False):
        await cog.webhook.callback(cog, i, True)
    assert "chiave di cifratura" in i.response.send_message.await_args.args[0]

    i = fake_interaction(guild=server, user=fake_member(user_id=1))
    server.me.guild_permissions = discord.Permissions.none()
    with patch.object(modulo.log_webhook_repo, "chiave_presente", return_value=True):
        await cog.webhook.callback(cog, i, True)
    assert "Gestisci webhook" in i.response.send_message.await_args.args[0]

    i = fake_interaction(guild=server, user=fake_member(user_id=1))
    server.me.guild_permissions = discord.Permissions(manage_webhooks=True)
    with patch.object(modulo.log_webhook_repo, "chiave_presente", return_value=True), \
            patch.object(modulo.db, "set_guild_setting", AsyncMock()) as scrive:
        await cog.webhook.callback(cog, i, True)
    scrive.assert_awaited_once_with(10, "log_webhook", True, 1)


async def test_comando_spegne_e_cancella_i_webhook():
    import cogs.utility.log_webhook as modulo

    cog = await _cog()
    i = fake_interaction(guild=fake_guild(10), user=fake_member(user_id=1))
    with patch.object(modulo.db, "set_guild_setting", AsyncMock()) as scrive, \
            patch.object(modulo, "spegni_server", AsyncMock(return_value=2)):
        await cog.webhook.callback(cog, i, False)
    scrive.assert_awaited_once_with(10, "log_webhook", False, 1)
    assert "Webhook cancellati: 2" in i.followup.send.await_args.args[0]
