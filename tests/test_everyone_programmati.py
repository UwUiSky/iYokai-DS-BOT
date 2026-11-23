"""
tests/test_everyone_programmati.py
==================================
UTL-110 (D124): messaggi programmati con @everyone o @here. Il permesso si rilegge al momento dell'invio,
c'è un tetto giornaliero per server, resta una riga nel log, `everyone=True` solo quando tutto passa.
"""

import discord
import pytest

from cogs.utility.scheduled_messages import ScheduledMessagesCog
from core import everyone_programmati as ev
from core import piani

AUTORE = 1
SERVER = 100


class _Canale(discord.TextChannel):
    def __init__(self, fallisce=False):
        self.id = 500
        self.fallisce = fallisce
        self.inviati: list[tuple[str, discord.AllowedMentions]] = []

    async def send(self, content=None, **kw):
        if self.fallisce:
            class _R:
                status, reason = 500, "x"
            raise discord.HTTPException(response=_R(), message="errore")
        self.inviati.append((content, kw.get("allowed_mentions")))
        return type("M", (), {"id": 9, "jump_url": "https://discord.com/x"})()


class _Permessi:
    def __init__(self, mention_everyone=False, administrator=False):
        self.mention_everyone, self.administrator = mention_everyone, administrator


class _Membro:
    def __init__(self, permessi):
        self.guild_permissions = permessi


class _Server:
    def __init__(self, canale, membri, owner_id=999):
        self.id, self.owner_id, self._c, self._m = SERVER, owner_id, canale, membri

    def get_channel(self, _):
        return self._c

    def get_member(self, uid):
        return self._m.get(uid)


class _Bot:
    def __init__(self, server):
        self._s = server
        self.avvisi: list[str] = []

    def get_guild(self, _):
        return self._s

    def get_user(self, uid):
        bot = self

        class _U:
            async def send(self, testo):
                bot.avvisi.append(testo)
        return _U()


@pytest.fixture
async def pronto(clean_db, monkeypatch):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    await database_module.db.ensure_guild_exists(SERVER)

    async def nessun_log(*a, **k):
        return None

    monkeypatch.setattr("cogs.utility.scheduled_messages.router.destinazione", nessun_log)
    return clean_db


async def _parte(canale, membri, testo="@everyone si gioca", **kw):
    server = _Server(canale, membri, **kw)
    bot = _Bot(server)
    await ScheduledMessagesCog(bot).handle_scheduled_message_fire(SERVER, AUTORE, {"channel_id": 500, "message": testo})
    return bot


def test_riconosce_everyone_e_here_solo_come_parole_intere():
    assert ev.contiene_menzione_di_massa("ciao @everyone") and ev.contiene_menzione_di_massa("@here!")
    assert not ev.contiene_menzione_di_massa("nessuna menzione @heretic")


async def test_con_il_permesso_parte_con_everyone(pronto):
    canale = _Canale()
    await _parte(canale, {AUTORE: _Membro(_Permessi(mention_everyone=True))})
    testo, menzioni = canale.inviati[0]
    assert testo == "@everyone si gioca" and menzioni.everyone is True


async def test_il_proprietario_non_ha_bisogno_del_permesso(pronto):
    canale = _Canale()
    await _parte(canale, {}, owner_id=AUTORE)
    assert canale.inviati[0][1].everyone is True


async def test_permesso_tolto_prima_dell_invio_parte_senza_menzione(pronto):
    canale = _Canale()
    bot = await _parte(canale, {AUTORE: _Membro(_Permessi())})  # alla creazione poteva, adesso no
    testo, menzioni = canale.inviati[0]
    assert menzioni.everyone is False
    assert "@everyone" not in testo and "everyone si gioca" in testo
    assert "non hai più il permesso" in bot.avvisi[0]
    assert await pronto.fetchval("SELECT count(*) FROM everyone_invii") == 0  # niente tetto consumato


async def test_autore_uscito_dal_server_non_puo(pronto):
    canale = _Canale()
    await _parte(canale, {})
    assert canale.inviati[0][1].everyone is False


async def test_tetto_giornaliero_per_server(pronto):
    await piani.imposta_limite("everyone_al_giorno", piani.GRATUITO, 2)
    membri = {AUTORE: _Membro(_Permessi(mention_everyone=True))}
    canale = _Canale()
    for _ in range(3):
        bot = await _parte(canale, membri)
    assert [m.everyone for _, m in canale.inviati] == [True, True, False]
    assert "tetto" in bot.avvisi[-1]
    await piani.concedi("server", SERVER, piani.PREMIUM, "mensile", giorni=30)
    await piani.imposta_limite("everyone_al_giorno", piani.PREMIUM, 5)
    await _parte(canale, membri)
    assert canale.inviati[-1][1].everyone is True  # il limite segue il livello


async def test_invio_fallito_restituisce_il_posto(pronto):
    membri = {AUTORE: _Membro(_Permessi(mention_everyone=True))}
    await _parte(_Canale(fallisce=True), membri)
    assert await pronto.fetchval("SELECT coalesce(sum(conteggio), 0) FROM everyone_invii") == 0


async def test_senza_menzione_non_serve_niente(pronto):
    canale = _Canale()
    await _parte(canale, {}, testo="ciao a tutti")
    assert canale.inviati[0][1].everyone is False
    assert await pronto.fetchval("SELECT count(*) FROM everyone_invii") == 0


async def test_invio_con_menzione_scrive_nel_log(pronto, monkeypatch):
    inviati = []

    class _Dest:
        pass

    async def destinazione(*a, **k):
        return _Dest()

    async def invia_a(dest, guild, tipo, **kw):
        inviati.append(kw["embed"].description)
        return True

    monkeypatch.setattr("cogs.utility.scheduled_messages.router.destinazione", destinazione)
    monkeypatch.setattr("cogs.utility.scheduled_messages.router.invia_a", invia_a)
    await _parte(_Canale(), {AUTORE: _Membro(_Permessi(mention_everyone=True))})
    assert len(inviati) == 1 and f"<@{AUTORE}>" in inviati[0]
