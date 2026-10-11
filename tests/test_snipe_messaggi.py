"""
tests/test_snipe_messaggi.py
============================
Snipe ed editsnipe (NF-03) e ghost ping cancellato da un moderatore (M 5.9).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.utility.snipe as modulo
from core import snipe_logic
from core.message_log_logic import Ignorati
from core.snipe_logic import SNIPE_TTL_SECONDS, RicordiSnipe, VoceRegistro, cancellato_da_altri, scaduto
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_text_channel

GUILD, CANALE = 100, 200


# ---------------------------------------------------------------- logica
def test_scadenza_dopo_cinque_minuti():
    ora = datetime.now(timezone.utc)
    assert not scaduto(ora - timedelta(seconds=SNIPE_TTL_SECONDS - 1), ora)
    assert scaduto(ora - timedelta(seconds=SNIPE_TTL_SECONDS + 1), ora)


def test_testo_snipe_taglia_a_4096_e_non_e_mai_vuoto():
    assert len(snipe_logic.testo_snipe("x" * 9000, [])) == 4096
    assert snipe_logic.testo_snipe("", []) == "*(nessun testo)*"
    assert "a.png" in snipe_logic.testo_snipe("ciao", ["a.png"])


def _v(entry_id=1, user=9, target=1, canale=CANALE, count=1, ts=1000.0):
    return VoceRegistro(entry_id, user, target, canale, count, ts)


def test_cancellato_da_altri_voce_nuova_attorno_all_evento():
    assert cancellato_da_altri([_v(ts=1000.0)], 1, CANALE, {}, 1000.5)
    assert not cancellato_da_altri([_v(user=1)], 1, CANALE, {}, 1000.0)  # lo ha cancellato lui
    assert not cancellato_da_altri([_v(target=5)], 1, CANALE, {}, 1000.0)  # messaggio di un altro
    assert not cancellato_da_altri([_v(canale=999)], 1, CANALE, {}, 1000.0)  # altro canale
    assert not cancellato_da_altri([], 1, CANALE, {}, 1000.0)


def test_un_moderatore_che_ha_cancellato_prima_non_nasconde_la_cancellazione_dell_autore():
    # il moderatore ha cancellato 5 secondi prima dell'evento: non è questa cancellazione
    assert not cancellato_da_altri([_v(ts=995.0)], 1, CANALE, {}, 1000.0)


def test_voce_unita_vecchia_conta_solo_se_il_conteggio_sale():
    visti = {}
    assert cancellato_da_altri([_v(ts=100.0)], 1, CANALE, visti, 100.5)  # prima volta, nuova
    assert not cancellato_da_altri([_v(ts=100.0)], 1, CANALE, visti, 900.0)  # stessa voce, stesso conteggio
    assert cancellato_da_altri([_v(ts=100.0, count=2)], 1, CANALE, visti, 901.0)  # unita: conteggio salito
    assert visti == {1: 2}


def test_ricordi_scadono_anche_in_scrittura_e_hanno_un_tetto_per_server():
    ricordi = RicordiSnipe(per_server=3)
    vecchio = datetime.now(timezone.utc) - timedelta(hours=1)

    class V:
        def __init__(self, guild_id, quando=None):
            self.guild_id, self.quando = guild_id, quando or datetime.now(timezone.utc)

    ricordi.set(1, V(7, vecchio))
    ricordi.set(2, V(7))  # scrivendo si pota la voce scaduta dello stesso server
    assert len(ricordi) == 1 and ricordi.get(1) is None
    for c in range(10, 20):
        ricordi.set(c, V(7))
    assert sum(1 for c in range(10, 20) if ricordi.get(c)) == 3  # i più vecchi di quel server escono
    ricordi.set(500, V(8))
    assert ricordi.get(500) is not None  # un altro server non viene cacciato


# ------------------------------------------------------------------- cog
@pytest.fixture
def ambiente(monkeypatch):
    attivi = {modulo.MODULE_SNIPE: True}
    db = MagicMock()
    db.is_module_active_for_guild = AsyncMock(side_effect=lambda g, m: attivi.get(m, False))
    db.get_guild_setting = AsyncMock(return_value=None)
    monkeypatch.setattr(modulo, "db", db)
    monkeypatch.setattr(modulo, "AUDIT_ATTESA_SECONDI", 0)
    ignora = MagicMock()
    ignora.carica = AsyncMock(return_value=Ignorati())
    monkeypatch.setattr(modulo, "log_ignora_repo", ignora)
    server = fake_guild(guild_id=GUILD)
    server.audit_logs = _Registro([])
    bot = MagicMock()
    bot.get_guild.return_value = server
    cog = modulo.SnipeCog(bot=bot)
    cog._test = (ignora, server)
    return cog, attivi


def _msg(testo="ciao", autore=42, bot=False, allegati=()):
    m = MagicMock()
    m.id = 70
    m.guild = fake_guild(guild_id=GUILD)
    m.channel = fake_text_channel(CANALE)
    m.author = fake_member(user_id=autore, bot=bot)
    m.author.id = autore
    m.author.display_name = "Mario"
    m.content = testo
    m.attachments = [MagicMock(filename=n) for n in allegati]
    m.jump_url = "https://discord.com/channels/1/2/3"
    return m


def _cancella(msg):
    p = MagicMock()
    p.guild_id, p.channel_id, p.message_id = GUILD, CANALE, msg.id
    p.cached_message = msg
    return p


def _ix():
    return fake_interaction(guild=fake_guild(guild_id=GUILD), channel=fake_text_channel(CANALE))


async def test_snipe_mostra_l_ultimo_messaggio_cancellato(ambiente):
    cog, _ = ambiente
    await cog.on_raw_message_delete(_cancella(_msg("addio", allegati=["a.png"])))
    ix = _ix()
    await cog.snipe.callback(cog, ix)
    embed = ix.response.send_message.call_args.kwargs["embed"]
    assert "addio" in embed.description and "a.png" in embed.description
    assert ix.response.send_message.call_args.kwargs["allowed_mentions"].users is False


async def test_snipe_senza_niente_lo_dice(ambiente):
    cog, _ = ambiente
    ix = _ix()
    await cog.snipe.callback(cog, ix)
    assert "Nessun messaggio" in ix.response.send_message.call_args.args[0]


async def test_snipe_scaduto_non_si_mostra_piu(ambiente):
    cog, _ = ambiente
    await cog.on_raw_message_delete(_cancella(_msg("vecchio")))
    voce = cog._ultimo_cancellato.get(CANALE)
    cog._ultimo_cancellato.set(
        CANALE, type(voce)(**{**voce.__dict__, "quando": datetime.now(timezone.utc) - timedelta(minutes=6)})
    )
    ix = _ix()
    await cog.snipe.callback(cog, ix)
    assert "Nessun messaggio" in ix.response.send_message.call_args.args[0]


async def test_interruttore_spento_non_ricorda_niente(ambiente):
    cog, attivi = ambiente
    attivi[modulo.MODULE_SNIPE] = False
    await cog.on_raw_message_delete(_cancella(_msg("segreto")))
    assert cog._ultimo_cancellato.get(CANALE) is None
    ix = _ix()
    await cog.snipe.callback(cog, ix)
    assert "non è attivo" in ix.response.send_message.call_args.args[0]


async def test_i_bot_e_i_messaggi_fuori_cache_non_si_ricordano(ambiente):
    cog, _ = ambiente
    await cog.on_raw_message_delete(_cancella(_msg(bot=True)))
    p = _cancella(_msg())
    p.cached_message = None
    await cog.on_raw_message_delete(p)
    assert cog._ultimo_cancellato.get(CANALE) is None


async def test_editsnipe_mostra_prima_e_dopo(ambiente):
    cog, _ = ambiente
    prima, dopo = _msg("prima"), _msg("dopo")
    await cog.on_message_edit(prima, dopo)
    ix = _ix()
    await cog.editsnipe.callback(cog, ix)
    embed = ix.response.send_message.call_args.kwargs["embed"]
    campi = {c.name: c.value for c in embed.fields}
    assert campi["Prima"] == "prima" and campi["Dopo"] == "dopo"


async def test_editsnipe_testo_lungo_resta_un_embed_valido(ambiente):
    cog, _ = ambiente
    await cog.on_message_edit(_msg("a" * 5000), _msg("b" * 5000))
    ix = _ix()
    await cog.editsnipe.callback(cog, ix)
    assert len(ix.response.send_message.call_args.kwargs["embed"]) <= 6000


async def test_modifica_senza_cambio_di_testo_non_si_ricorda(ambiente):
    cog, _ = ambiente
    await cog.on_message_edit(_msg("uguale"), _msg("uguale"))
    assert cog._ultima_modifica.get(CANALE) is None


async def test_cio_che_toglie_un_moderatore_non_si_ricorda(ambiente):
    cog, _ = ambiente
    _, server = cog._test
    server.audit_logs = _Registro([_voce_registro(9, 42, CANALE, secondi_fa=0)])
    await cog.on_raw_message_delete(_cancella(_msg("tolto dal mod")))
    assert cog._ultimo_cancellato.get(CANALE) is None


async def test_snipe_rispetta_log_ignora(ambiente):
    cog, _ = ambiente
    ignora, _ = cog._test
    ignora.carica = AsyncMock(return_value=Ignorati(utenti=frozenset({42})))
    await cog.on_raw_message_delete(_cancella(_msg("non ricordare")))
    assert cog._ultimo_cancellato.get(CANALE) is None
    ignora.carica = AsyncMock(return_value=Ignorati(canali=frozenset({CANALE})))
    await cog.on_message_edit(_msg("a"), _msg("b"))
    assert cog._ultima_modifica.get(CANALE) is None


# ----------------------------------------------------------- ghost ping 5.9
class _Registro:
    def __init__(self, voci):
        self.voci = voci

    def __call__(self, **kw):
        voci = self.voci

        async def gen():
            for v in voci:
                yield v

        return gen()


def _voce_registro(da, bersaglio, canale, secondi_fa=1):
    v = MagicMock()
    v.id = 321
    v.extra.count = 1
    v.user_id = da
    v.target = MagicMock(id=bersaglio)
    v.extra.channel = MagicMock(id=canale)
    v.created_at = discord.utils.utcnow() - timedelta(seconds=secondi_fa)
    return v


async def _ghost_ping(monkeypatch, voci, abilitato=True):
    monkeypatch.setattr(modulo, "AUDIT_ATTESA_SECONDI", 0)
    log_channel = fake_text_channel(999)
    log_channel.send = AsyncMock()
    server = fake_guild(guild_id=GUILD)
    server.audit_logs = _Registro(voci)
    monkeypatch.setattr(modulo.router, "destinazione", AsyncMock(return_value=log_channel))
    bot = MagicMock()
    bot.get_guild.return_value = server
    db = MagicMock()
    db.is_module_active_for_guild = AsyncMock(side_effect=lambda g, m: m == modulo.MODULE_GHOST_PING)
    db.get_guild_setting = AsyncMock(return_value=999)
    monkeypatch.setattr(modulo, "db", db)
    cog = modulo.SnipeCog(bot)
    msg = _msg("ciao @tu")
    msg.mentions = [MagicMock(id=5)]
    msg.mention_everyone = False
    await cog.on_message(msg)
    await cog.on_raw_message_delete(_cancella(msg))
    return log_channel


async def test_ghost_ping_cancellato_dall_autore_segnala(monkeypatch):
    canale = await _ghost_ping(monkeypatch, [])
    canale.send.assert_awaited_once()


async def test_ghost_ping_cancellato_da_un_moderatore_non_segnala(monkeypatch):
    canale = await _ghost_ping(monkeypatch, [_voce_registro(9, 42, CANALE)])
    canale.send.assert_not_awaited()


async def test_ghost_ping_dell_autore_con_un_moderatore_di_5_secondi_prima_segnala(monkeypatch):
    canale = await _ghost_ping(monkeypatch, [_voce_registro(9, 42, CANALE, secondi_fa=5)])
    canale.send.assert_awaited_once()


async def test_ghost_ping_registro_illeggibile_segnala_come_prima(monkeypatch):
    def vieta(**kw):
        raise discord.Forbidden(MagicMock(status=403, reason="x"), "no")

    monkeypatch.setattr(modulo, "AUDIT_ATTESA_SECONDI", 0)
    log_channel = fake_text_channel(999)
    log_channel.send = AsyncMock()
    server = fake_guild(guild_id=GUILD)
    server.audit_logs = vieta
    monkeypatch.setattr(modulo.router, "destinazione", AsyncMock(return_value=log_channel))
    bot = MagicMock()
    bot.get_guild.return_value = server
    db = MagicMock()
    db.is_module_active_for_guild = AsyncMock(side_effect=lambda g, m: m == modulo.MODULE_GHOST_PING)
    db.get_guild_setting = AsyncMock(return_value=999)
    monkeypatch.setattr(modulo, "db", db)
    cog = modulo.SnipeCog(bot)
    msg = _msg()
    msg.mentions = [MagicMock(id=5)]
    msg.mention_everyone = False
    await cog.on_message(msg)
    await cog.on_raw_message_delete(_cancella(msg))
    log_channel.send.assert_awaited_once()
