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


# LOG-025: righe vicine raggruppate in un solo messaggio
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


# LOG-025: raggruppamento entro 10 embed e 6000 caratteri
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


# ---------------------------------------------------------------- log a nome utente (D74, #160)
@pytest.mark.parametrize("nome,atteso", [
    ("Giulia", "Giulia · log"),
    ("Discord Staff", "Staff · log"),
    ("xCLYDEx", "xx · log"),
    ("dis​cord", "· log".strip()),  # il carattere invisibile non nasconde la parola
    ("", "utente · log"),
    ("\x00\x1b\n", "utente · log"),
    ("ＤＩＳＣＯＲＤ", "utente · log"),
])
def test_nome_pulito(nome, atteso):
    assert lw.nome_a_nome_utente(nome).endswith(" · log")
    if nome != "dis​cord":
        assert lw.nome_a_nome_utente(nome) == atteso


def test_nome_mai_oltre_80_e_mai_vuoto_e_senza_parole_vietate():
    lungo = lw.nome_a_nome_utente("a" * 500)
    assert len(lungo) == 80 and lungo.endswith(" · log")
    for brutto in ("dis​cord", "dDiIsScCoOrRdD", "clyde\x07", "disdiscordcord"):
        pulito = lw.nome_a_nome_utente(brutto)
        assert 1 <= len(pulito) <= 80
        assert "discord" not in pulito.lower() and "clyde" not in pulito.lower()
        assert not any(ord(c) < 32 for c in pulito)


def _autore(nome="Giulia"):
    a = MagicMock()
    a.display_name = nome
    a.display_avatar.url = "https://cdn.example/a.png"
    return a


async def test_a_nome_utente_ogni_invio_ha_nome_avatar_e_nessuna_menzione(monkeypatch):
    monkeypatch.setattr(lw, "PAUSA_TRA_NOMI", 0.01)
    monkeypatch.setattr(lw, "a_nome_utente_acceso", AsyncMock(return_value=True))
    web = _webhook()
    dest = lw.CanaleWebhook(_canale(), web)
    assert await lw.invia_a_nome_utente(dest, _embed("1"), _autore("Giulia")) is True
    assert await lw.invia_a_nome_utente(dest, _embed("2"), _autore("Marco")) is True
    await asyncio.sleep(0.15)
    assert web.send.await_count == 2
    primo, secondo = (c.kwargs for c in web.send.await_args_list)
    assert primo["username"] == "Giulia · log" and secondo["username"] == "Marco · log"
    assert primo["avatar_url"] == "https://cdn.example/a.png"
    assert primo["allowed_mentions"].everyone is False and primo["allowed_mentions"].users is False


async def test_a_nome_utente_spento_o_canale_normale_non_lo_prende(monkeypatch):
    web = _webhook()
    dest = lw.CanaleWebhook(_canale(), web)
    monkeypatch.setattr(lw, "a_nome_utente_acceso", AsyncMock(return_value=False))
    assert await lw.invia_a_nome_utente(dest, _embed(), _autore()) is False
    monkeypatch.setattr(lw, "a_nome_utente_acceso", AsyncMock(return_value=True))
    assert await lw.invia_a_nome_utente(_canale(), _embed(), _autore()) is False  # non e' un webhook
    assert await lw.invia_a_nome_utente(dest, _embed(), None) is False
    web.send.assert_not_awaited()


async def test_a_nome_utente_ha_un_tetto_oltre_il_quale_esce_raggruppato(monkeypatch):
    monkeypatch.setattr(lw, "PAUSA_TRA_NOMI", 5)
    monkeypatch.setattr(lw, "a_nome_utente_acceso", AsyncMock(return_value=True))
    web = _webhook()
    dest = lw.CanaleWebhook(_canale(), web)
    for i in range(lw.MAX_NOMI_IN_CODA + 3):
        await lw.invia_a_nome_utente(dest, _embed(str(i)), _autore())
    await asyncio.sleep(0.05)
    chiamate = [c.kwargs for c in web.send.await_args_list]
    assert sum("username" in k for k in chiamate) == 1  # il primo parte, gli altri aspettano la pausa
    assert len(dest._coda_nomi) == lw.MAX_NOMI_IN_CODA - 1
    raggruppate = [k for k in chiamate if "embeds" in k]  # i tre in piu': un solo messaggio, senza nome
    assert len(raggruppate) == 1 and len(raggruppate[0]["embeds"]) == 3 and "username" not in raggruppate[0]
    dest._task_nomi.cancel()
    await dest.svuota_finale()


async def test_a_nome_utente_webhook_cancellato_torna_al_canale(monkeypatch):
    monkeypatch.setattr(lw, "a_nome_utente_acceso", AsyncMock(return_value=True))
    web = _webhook()
    web.send.side_effect = discord.NotFound(MagicMock(status=404), "x")
    canale = _canale()
    canale.send = AsyncMock()
    dest = lw.CanaleWebhook(canale, web)
    await lw.invia_a_nome_utente(dest, _embed("x"), _autore())
    await asyncio.sleep(0.05)
    canale.send.assert_awaited_once()
    assert canale.send.await_args.kwargs["allowed_mentions"].users is False


async def test_comando_a_nome_utente_base_spento_e_serve_il_webhook():
    import cogs.utility.log_webhook as modulo

    cog = await _cog()
    i = fake_interaction(guild=fake_guild(10), user=fake_member(user_id=1))
    await cog.webhook.callback(cog, i, None, None)
    assert "almeno" in i.response.send_message.await_args.args[0]

    i = fake_interaction(guild=fake_guild(10), user=fake_member(user_id=1))
    with patch.object(modulo, "acceso", AsyncMock(return_value=False)), \
            patch.object(modulo.db, "set_guild_setting", AsyncMock()) as scrive:
        await cog.webhook.callback(cog, i, None, True)
    scrive.assert_not_awaited()
    assert "Prima accendi" in i.response.send_message.await_args.args[0]

    i = fake_interaction(guild=fake_guild(10), user=fake_member(user_id=1))
    with patch.object(modulo, "acceso", AsyncMock(return_value=True)), \
            patch.object(modulo.db, "set_guild_setting", AsyncMock()) as scrive:
        await cog.webhook.callback(cog, i, None, True)
    scrive.assert_awaited_once_with(10, "log_webhook_utente", True, 1)


async def test_il_log_dei_messaggi_passa_l_autore_solo_senza_file(monkeypatch):
    from cogs.logging.message_logs import MessageLogsCog

    cog = MessageLogsCog(MagicMock())
    dest = lw.CanaleWebhook(_canale(), _webhook())
    import cogs.logging.message_logs as ml

    monkeypatch.setattr(ml.log_eventi_repo, "evento_acceso", AsyncMock(return_value=True))
    monkeypatch.setattr(ml.db, "get_guild_setting", AsyncMock(return_value=None))
    monkeypatch.setattr(ml.router, "destinazione", AsyncMock(return_value=dest))
    nome = AsyncMock(return_value=True)
    monkeypatch.setattr(ml.log_webhook, "invia_a_nome_utente", nome)
    invia = AsyncMock()
    monkeypatch.setattr(ml.router, "invia_a", invia)
    server = fake_guild(10)
    await cog._scrivi(server, "message_edit", autore=_autore(), embed=_embed())
    nome.assert_awaited_once()
    invia.assert_not_awaited()
    await cog._scrivi(server, "message_delete", autore=_autore(), embed=_embed(), files=[object()])
    assert nome.await_count == 1 and invia.await_count == 1  # con file: come sempre
