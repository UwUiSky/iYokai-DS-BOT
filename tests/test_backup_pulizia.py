"""
tests/test_backup_pulizia.py
============================
Cancellazione facoltativa di canali e ruoli prima del caricamento (BKP-004, D133):
solo il proprietario, conferma in due passi, cose protette, interruzione.
Funzioni coperte: BKP-004
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import discord
import pytest

import cogs.utility.backup as backup_module
from cogs.utility.backup import BackupCog, ScegliPartiView
from core import backup_pulizia_logic as pulizia

GUILD = 920044


class _Ruolo:
    def __init__(self, id, pos, managed=False, default=False, errore=None):
        self.id, self.position, self.managed, self._default, self.errore = id, pos, managed, default, errore
        self.cancellato = False

    def is_default(self):
        return self._default

    def __ge__(self, altro):
        return self.position >= altro.position

    async def delete(self, reason=None):
        assert reason and len(reason) <= 512
        if self.errore:
            raise self.errore
        self.cancellato = True


class _Canale:
    def __init__(self, id, errore=None):
        self.id, self.errore, self.cancellato = id, errore, False

    async def delete(self, reason=None):
        assert reason and len(reason) <= 512
        if self.errore:
            raise self.errore
        self.cancellato = True


def _http(status):
    return discord.HTTPException(SimpleNamespace(status=status, reason="x"), "errore")


def _guild(owner_id=1, canali=(), ruoli=()):
    bot_ruolo = _Ruolo(900, 10)
    everyone = _Ruolo(GUILD, 0, default=True)
    g = SimpleNamespace(
        id=GUILD, owner_id=owner_id, channels=list(canali),
        roles=[everyone, bot_ruolo, *ruoli], default_role=everyone,
        me=SimpleNamespace(top_role=bot_ruolo),
        rules_channel=None, public_updates_channel=None, safety_alerts_channel=None,
    )
    return g


async def _nessuna_pausa(_s):
    pass


async def test_non_si_tocca_il_protetto():
    corrente, regole, altro = _Canale(1), _Canale(2), _Canale(3)
    semplice = _Ruolo(10, 5)
    gestito, sopra, pari = _Ruolo(11, 5, managed=True), _Ruolo(12, 11), _Ruolo(13, 10)
    g = _guild(canali=[corrente, regole, altro], ruoli=[semplice, gestito, sopra, pari])
    g.rules_channel = regole
    r = await pulizia.esegui(g, 1, 1, None, True, True, pausa=_nessuna_pausa)
    assert [c.cancellato for c in (corrente, regole, altro)] == [False, False, True]
    assert [x.cancellato for x in (semplice, gestito, sopra, pari)] == [True, False, False, False]
    assert not g.default_role.cancellato and not g.roles[1].cancellato  # @everyone e ruolo del bot
    assert (r.canali, r.ruoli, r.interrotta) == (1, 1, False)
    assert r.saltati == 6 and "non toccati" in r.testo()


async def test_canale_genitore_del_thread_si_salva():
    padre, altro = _Canale(5), _Canale(6)
    g = _guild(canali=[padre, altro])
    await pulizia.esegui(g, 1, 99, 5, True, False, pausa=_nessuna_pausa)
    assert (padre.cancellato, altro.cancellato) == (False, True)


async def test_scelte_separate_canali_e_ruoli():
    c, ru = _Canale(1), _Ruolo(10, 5)
    g = _guild(canali=[c], ruoli=[ru])
    await pulizia.esegui(g, 1, 99, None, False, True, pausa=_nessuna_pausa)
    assert (c.cancellato, ru.cancellato) == (False, True)


async def test_non_proprietario_non_cancella_mai():
    c = _Canale(1)
    g = _guild(owner_id=2, canali=[c])
    with pytest.raises(pulizia.PuliziaNegata):
        await pulizia.esegui(g, 1, 99, None, True, True, pausa=_nessuna_pausa)
    assert not c.cancellato


async def test_canale_richiesto_dalla_community_si_salta_con_nota():
    rif, altro = _Canale(1, errore=_http(400)), _Canale(2)
    g = _guild(canali=[rif, altro])
    r = await pulizia.esegui(g, 1, 99, None, True, False, pausa=_nessuna_pausa)
    assert not r.interrotta and altro.cancellato and r.canali == 1 and r.saltati == 1


async def test_errore_vero_interrompe_e_si_ferma():
    primo, rotto, dopo = _Canale(1), _Canale(2, errore=_http(500)), _Canale(3)
    g = _guild(canali=[primo, rotto, dopo])
    r = await pulizia.esegui(g, 1, 99, None, True, False, pausa=_nessuna_pausa)
    assert r.interrotta and primo.cancellato and not dopo.cancellato


async def test_annullo_ferma_la_cancellazione():
    primo, dopo = _Canale(1), _Canale(2)
    g = _guild(canali=[primo, dopo])

    async def avanza(_p, fatti, _t):
        return fatti == 2

    r = await pulizia.esegui(g, 1, 99, None, True, False, avanza=avanza, pausa=_nessuna_pausa)
    assert r.interrotta and primo.cancellato and not dopo.cancellato


def test_motivo_audit_entro_512():
    assert len(pulizia.motivo_audit(10**30)) <= 512


# --- menu e cog ------------------------------------------------------------

class _Risposte:
    def __init__(self):
        self.messaggi = []

    async def send_message(self, contenuto=None, **kw):
        self.messaggi.append((contenuto, kw))

    async def defer(self, **kw):
        pass

    async def edit_message(self, **kw):
        self.messaggi.append((kw.get("content"), kw))


class _CanaleTesto(_Canale):
    def __init__(self, id):
        super().__init__(id)
        self.inviati = []
        self.parent_id = None

    async def send(self, testo):
        self.inviati.append(testo)


def _interazione(guild, user_id=1):
    return SimpleNamespace(
        guild=guild, user=SimpleNamespace(id=user_id, guild_permissions=SimpleNamespace(administrator=True)),
        response=_Risposte(), followup=_Risposte(), channel=guild.channels[0], locale=None,
    )


@pytest.fixture
def cog(monkeypatch):
    registrati, caricamenti = [], []

    class _Repo:
        async def avvia_caricamento(self, *a):
            caricamenti.append(a)
            return 1 if len(caricamenti) == 1 else None

        async def aggiorna_caricamento(self, *a):
            return False

        async def chiudi_caricamento(self, *a):
            registrati.append(a)

        async def registra(self, *a):
            pass

    monkeypatch.setattr(backup_module, "backup_struttura_repo", _Repo())
    c = BackupCog(bot=None)
    c.chiusure = registrati
    return c


def _vista(cog, guild, user_id):
    dati = {"versione": 1, "ruoli": [{"nome": "r", "permessi": 0}], "canali": [{"nome": "c", "tipo": "text"}]}
    return ScegliPartiView(cog, user_id, dati, "copia #1", guild=guild)


def _bottoni(view):
    return {getattr(i, "label", ""): i for i in view.children if isinstance(i, discord.ui.Button)}


async def test_proprietario_vede_le_scelte_e_admin_no(cog):
    canale = _CanaleTesto(1)
    g = _guild(owner_id=1, canali=[canale])
    assert any("canali" in k for k in _bottoni(_vista(cog, g, 1)))
    g2 = _guild(owner_id=2, canali=[canale])
    assert not any("cancella" in k.lower() for k in _bottoni(_vista(cog, g2, 1)))


async def test_admin_forzando_il_callback_viene_rifiutato(cog, monkeypatch):
    canale, altro = _CanaleTesto(1), _Canale(2)
    g = _guild(owner_id=2, canali=[canale, altro])
    view = _vista(cog, g, 1)
    i = _interazione(g)
    await view.alterna_canali.callback(i)
    assert not view.cancella_canali
    view.cancella_canali = True  # anche se lo stato fosse stato forzato
    await view.conferma.callback(i)
    assert not altro.cancellato
    assert "proprietario" in i.response.messaggi[-1][0].lower()


async def test_due_passi_e_prima_si_cancella_poi_si_carica(cog, monkeypatch):
    canale, altro = _CanaleTesto(1), _Canale(2)
    ruolo = _Ruolo(10, 5)
    g = _guild(owner_id=1, canali=[canale, altro], ruoli=[ruolo])
    ordine = []

    class _Caricatore:
        def __init__(self, *a, **k):
            pass

        async def esegui(self):
            ordine.append(("carica", altro.cancellato, ruolo.cancellato))
            return SimpleNamespace(annullato=False, testo=lambda: "Creati: 1")

    monkeypatch.setattr(backup_module.struttura, "Caricatore", _Caricatore)
    view = _vista(cog, g, 1)
    i = _interazione(g)
    await view.alterna_canali.callback(i)
    await view.alterna_ruoli.callback(i)
    await view.conferma.callback(i)
    # primo passo: solo riepilogo con i numeri, niente cancellato
    assert not altro.cancellato and not cog._lavori
    assert "1** canali" in i.response.messaggi[-1][0] and "1** ruoli" in i.response.messaggi[-1][0]
    conferma = i.response.messaggi[-1][1]["view"]
    await conferma.si.callback(i)
    await asyncio.gather(*cog._lavori)
    assert ordine == [("carica", True, True)]
    assert "Cancellati: 1 canali, 1 ruoli" in canale.inviati[0] and "Creati: 1" in canale.inviati[0]
    assert not canale.cancellato  # il canale del lavoro è salvo


async def test_conferma_ricontrolla_il_proprietario(cog, monkeypatch):
    canale, altro = _CanaleTesto(1), _Canale(2)
    g = _guild(owner_id=1, canali=[canale, altro])
    view = _vista(cog, g, 1)
    i = _interazione(g)
    await view.alterna_canali.callback(i)
    await view.conferma.callback(i)
    conferma = i.response.messaggi[-1][1]["view"]
    g.owner_id = 3  # la proprietà passa ad altri prima del clic
    await conferma.si.callback(i)
    assert not altro.cancellato and not cog._lavori
    assert "proprietario" in i.response.messaggi[-1][0].lower()


async def test_cancellazione_interrotta_non_carica(cog, monkeypatch):
    canale, rotto = _CanaleTesto(1), _Canale(2, errore=_http(500))
    g = _guild(owner_id=1, canali=[canale, rotto])
    partito = []

    class _Caricatore:
        def __init__(self, *a, **k):
            partito.append(1)

        async def esegui(self):
            return SimpleNamespace(annullato=False, testo=lambda: "x")

    monkeypatch.setattr(backup_module.struttura, "Caricatore", _Caricatore)
    view = _vista(cog, g, 1)
    i = _interazione(g)
    await view.alterna_canali.callback(i)
    await view.conferma.callback(i)
    await i.response.messaggi[-1][1]["view"].si.callback(i)
    await asyncio.gather(*cog._lavori)
    assert partito == []
    assert "non è partito" in canale.inviati[0]
    assert cog.chiusure[0][1] == "annullato"
