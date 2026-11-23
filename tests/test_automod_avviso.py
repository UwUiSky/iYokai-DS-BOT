"""
tests/test_automod_avviso.py
============================
Avviso all'utente quando l'AutoMod cancella un messaggio (#116, D110): DM con i motivi, messaggio breve nel
canale se i DM sono chiusi, impostazione del server, tetto per persona, testo nella lingua del server.
"""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.moderation._shared as modulo_shared
from core import automod_avviso as av
from tests.support.discord_fakes import fake_guild, fake_member, fake_message, fake_text_channel


class ArchivioFinto:
    def __init__(self, **valori):
        self.valori = valori
        self.scritti = []

    async def get_guild_setting(self, guild_id, chiave, default=None):
        return self.valori.get(chiave, default)

    async def set_guild_setting(self, guild_id, chiave, valore, changed_by=None):
        self.scritti.append((chiave, valore, changed_by))
        self.valori[chiave] = valore


def _messaggio():
    server = fake_guild(guild_id=666, name="Server di prova")
    autore = fake_member(user_id=4242, name="Mario")
    autore.guild = server
    msg = fake_message(author=autore, guild=server, content="testo segreto del messaggio")
    msg.channel = fake_text_channel(channel_id=111)
    msg.channel.mention = "<#111>"
    msg.channel.send = AsyncMock()
    return msg


@pytest.fixture(autouse=True)
def pulito():
    av.limitatore.svuota()
    yield
    av.limitatore.svuota()


@pytest.fixture
def dm(monkeypatch):
    finto = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr(modulo_shared, "try_dm_message", finto)
    return finto


# ---------------------------------------------------------------- opzioni
async def test_di_base_l_avviso_e_acceso_e_senza_testo():
    opz = await av.leggi(1, ArchivioFinto())
    assert opz.attivo is True and opz.testo == ""


async def test_leggi_ignora_valori_storti():
    opz = await av.leggi(1, ArchivioFinto(automod_avviso_attivo="si", automod_avviso_testo=5))
    assert opz.attivo is True and opz.testo == ""
    opz = await av.leggi(1, ArchivioFinto(automod_avviso_attivo=False, automod_avviso_testo="x" * 900))
    assert opz.attivo is False and len(opz.testo) == av.MAX_TESTO


async def test_imposta_scrive_e_toglie_il_testo():
    arch = ArchivioFinto()
    await av.imposta(1, False, "Ciao {utente}", 9, arch)
    assert (av.SETTING_ATTIVO, False, 9) in arch.scritti
    assert (av.SETTING_TESTO, "Ciao {utente}", 9) in arch.scritti
    await av.imposta(1, None, "  ", 9, arch)  # testo vuoto = torna quello di base; l'interruttore resta
    assert arch.scritti[-1] == (av.SETTING_TESTO, None, 9)
    assert len(arch.scritti) == 3


async def test_imposta_rifiuta_testo_troppo_lungo():
    with pytest.raises(ValueError):
        await av.imposta(1, None, "x" * (av.MAX_TESTO + 1), 9, ArchivioFinto())


# ---------------------------------------------------------------- testo
def test_segnaposto_a_elenco_chiuso():
    valori = {"server": "S", "canale": "C", "regole": "R", "utente": "U"}
    assert av.espandi("{server} {canale} {regole} {utente}", valori) == "S C R U"
    assert av.espandi("{moderatore} {motivo} {x}", valori) == "{moderatore} {motivo} {x}"  # sconosciuti: restano


def test_elenco_regole_troncato():
    nomi = [f"Regola numero {i} " + "x" * 100 for i in range(9)]
    testo = av.elenco_regole(nomi)
    assert testo.count("Regola numero") == av.MAX_REGOLE_ELENCO
    assert testo.endswith("…") and len(testo) <= av.MAX_ELENCO
    assert all(len(riga) <= av.MAX_NOME_REGOLA + 3 for riga in testo.split(", ") if "Regola" in riga)


def test_elenco_regole_senza_doppioni_e_senza_menzioni():
    testo = av.elenco_regole(["Anti-Link", "Anti-Link", "@everyone <@1> <@&2>"])
    assert testo.count("Anti-Link") == 1
    assert "<@" not in testo and "@everyone" not in testo


# ---------------------------------------------------------------- tetto
def test_tetto_un_avviso_ogni_30_secondi():
    lim = av.LimitatoreAvvisi()
    assert lim.puo_avvisare(1, 2, 100.0) is True
    assert lim.puo_avvisare(1, 2, 129.0) is False
    assert lim.puo_avvisare(1, 2, 130.0) is True
    assert lim.puo_avvisare(1, 3, 100.0) is True  # un'altra persona ha il suo tetto


def test_tetto_cinque_in_dieci_minuti():
    lim = av.LimitatoreAvvisi()
    for i in range(5):
        assert lim.puo_avvisare(1, 2, 1000.0 + 31 * i) is True
    assert lim.puo_avvisare(1, 2, 1000.0 + 31 * 5) is False
    assert lim.puo_avvisare(1, 2, 1000.0 + 31 * 5 + 600) is True  # i vecchi escono dalla finestra


def test_il_limitatore_ha_un_tetto_di_memoria():
    lim = av.LimitatoreAvvisi(max_persone=10)
    for i in range(100):
        lim.puo_avvisare(1, i, 1.0)
    assert len(lim) <= 10


# ---------------------------------------------------------------- invio
async def test_dm_con_motivi_e_senza_contenuto(dm):
    msg = _messaggio()
    esito = await av.avvisa(msg, [("anti_caps", None), ("anti_link", None)], ArchivioFinto())
    assert esito == av.ESITO_DM
    embed = dm.await_args.args[1]
    visto = f"{embed.title} {embed.description} " + " ".join(f.value for f in embed.fields)
    assert "Anti-Caps" in visto and "Anti-Link" in visto
    assert "testo segreto" not in visto  # il contenuto del messaggio non torna all'utente
    msg.channel.send.assert_not_called()


async def test_nome_della_regola_personale_nel_motivo(dm):
    await av.avvisa(_messaggio(), [("regola_x", "Niente spoiler")], ArchivioFinto())
    embed = dm.await_args.args[1]
    assert "Niente spoiler" in " ".join(f.value for f in embed.fields)


async def test_spento_non_scrive_a_nessuno(dm):
    msg = _messaggio()
    esito = await av.avvisa(msg, [("anti_caps", None)], ArchivioFinto(automod_avviso_attivo=False))
    assert esito == av.ESITO_SPENTO
    dm.assert_not_called()
    msg.channel.send.assert_not_called()


async def test_testo_del_server_con_segnaposto(dm):
    arch = ArchivioFinto(automod_avviso_testo="Ehi {utente}, su {server} in {canale}: {regole}")
    await av.avvisa(_messaggio(), [("anti_caps", None)], arch)
    embed = dm.await_args.args[1]
    assert embed.description == "Ehi Mario, su Server di prova in <#111>: Anti-Caps"


async def test_dm_chiusi_messaggio_nel_canale_che_si_cancella(dm):
    dm.return_value = None
    msg = _messaggio()
    esito = await av.avvisa(msg, [("anti_link", None)], ArchivioFinto())
    assert esito == av.ESITO_CANALE
    msg.channel.send.assert_awaited_once()
    args, kw = msg.channel.send.await_args
    assert kw["delete_after"] == 8
    assert args[0].startswith("<@4242>")
    menzioni = kw["allowed_mentions"]
    assert menzioni.everyone is False and menzioni.roles is False
    assert [u.id for u in menzioni.users] == [4242]
    assert len(args[0]) <= 400


async def test_dm_chiusi_e_canale_chiuso_non_solleva(dm):
    dm.return_value = None
    msg = _messaggio()
    risposta = MagicMock(status=403, reason="x")
    msg.channel.send.side_effect = discord.Forbidden(risposta, "no")
    assert await av.avvisa(msg, [("anti_link", None)], ArchivioFinto()) == av.ESITO_NESSUNO


async def test_errore_nel_dm_non_solleva(dm):
    dm.side_effect = RuntimeError("boom")
    msg = _messaggio()
    assert await av.avvisa(msg, [("anti_link", None)], ArchivioFinto()) == av.ESITO_NESSUNO
    msg.channel.send.assert_not_called()


async def test_database_che_non_risponde_non_solleva(dm):
    class Rotto:
        async def get_guild_setting(self, *a, **k):
            raise RuntimeError("db giu")

    assert await av.avvisa(_messaggio(), [("anti_link", None)], Rotto()) == av.ESITO_NESSUNO
    dm.assert_not_called()


async def test_tetto_per_persona_blocca_il_secondo_avviso(dm):
    msg = _messaggio()
    assert await av.avvisa(msg, [("anti_link", None)], ArchivioFinto(), ora=500.0) == av.ESITO_DM
    assert await av.avvisa(msg, [("anti_link", None)], ArchivioFinto(), ora=510.0) == av.ESITO_TETTO
    assert dm.await_count == 1


async def test_bot_e_webhook_non_si_avvisano(dm):
    msg = _messaggio()
    msg.author = fake_member(user_id=5, bot=True)
    assert await av.avvisa(msg, [("anti_link", None)], ArchivioFinto()) == av.ESITO_NESSUNO
    dm.assert_not_called()


async def test_testo_nella_lingua_del_server(dm, monkeypatch):
    async def inglese(guild_id):
        return "en"

    monkeypatch.setattr("core.i18n.lingua_server", inglese)
    await av.avvisa(_messaggio(), [("anti_caps", None)], ArchivioFinto())
    embed = dm.await_args.args[1]
    assert "removed" in embed.description.lower()
    assert "Caps" in " ".join(f.value for f in embed.fields)
    assert "rimosso" not in embed.description.lower()


# ---------------------------------------------------------------- dentro l'AutoMod
from tests.test_automod_filtri_messaggi import (  # noqa: E402
    _interazione_admin, _messaggio as _messaggio_cog, _scelta, _violazioni_registrate, cog,  # noqa: F401
)


async def _regola_link(cog):
    await cog.anti_link_mode.callback(cog, _interazione_admin(), _scelta("blacklist"))
    await cog.anti_link_domain.callback(cog, _interazione_admin(), _scelta("add"), _scelta("blacklist"), "evil.com")


async def test_messaggio_cancellato_avvisa_con_il_motivo(cog, dm):
    await _regola_link(cog)
    msg = _messaggio_cog("guardate https://evil.com/x")
    msg.channel.send = AsyncMock()
    await cog.on_message(msg)
    msg.delete.assert_awaited_once()
    embed = dm.await_args.args[1]
    assert "Anti-Link" in " ".join(f.value for f in embed.fields)
    assert dm.await_args.args[0] is msg.author


async def test_messaggio_pulito_non_avvisa(cog, dm):
    await _regola_link(cog)
    await cog.on_message(_messaggio_cog("ciao a tutti"))
    dm.assert_not_called()


async def test_errore_dell_avviso_non_ferma_cancellazione_e_log(cog, dm):
    await _regola_link(cog)
    dm.side_effect = RuntimeError("boom")
    msg = _messaggio_cog("https://evil.com/x")
    await cog.on_message(msg)
    msg.delete.assert_awaited_once()
    assert await _violazioni_registrate() == ["anti_link"]


async def test_avviso_spento_nel_server_non_scrive(cog, dm, monkeypatch):
    await _regola_link(cog)
    db_finto = modulo_shared.db
    db_finto.get_guild_setting.side_effect = lambda g, k, d=None: False if k == av.SETTING_ATTIVO else d
    import cogs.automod.automod as modulo_automod
    monkeypatch.setattr(modulo_automod, "db", db_finto)
    msg = _messaggio_cog("https://evil.com/x")
    await cog.on_message(msg)
    msg.delete.assert_awaited_once()
    dm.assert_not_called()
