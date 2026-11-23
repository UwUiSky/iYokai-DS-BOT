"""
tests/test_piani.py
===================
CFG-040, CFG-041, AI-003 (D59, D127): livello da più fonti, limiti per livello, prezzi e sconti, chiavi proprie cifrate.
"""

from types import SimpleNamespace

import pytest

from core import ai_chiavi_proprie as chiavi
from core import piani

CHIAVE_CIFRATURA = "A" * 43 + "="


@pytest.fixture
async def pronto(clean_db, monkeypatch):
    import core.database as database_module
    from core import premium as premium_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    monkeypatch.setattr(premium_module, "config", SimpleNamespace(PREMIUM_ALPHA_UNLOCK_ALL=False, MAIN_GUILD_ID=999, PREMIUM_BOOST_GUILD_IDS=""))
    monkeypatch.setattr(chiavi, "_chiave_cifratura", lambda: CHIAVE_CIFRATURA)
    await database_module.db.ensure_guild_exists(100)
    return clean_db


class _Guild:
    def __init__(self, gid, owner_id=0, membri=None):
        self.id, self.owner_id, self._m = gid, owner_id, membri or {}

    def get_member(self, uid):
        return self._m.get(uid)


class _Bot:
    def __init__(self, *guild):
        self._g = {g.id: g for g in guild}

    def get_guild(self, gid):
        return self._g.get(gid)


async def test_senza_fonti_tutto_gratuito(pronto):
    assert await piani.livello_server(100) == piani.GRATUITO
    assert await piani.livello_utente(5) == piani.GRATUITO


async def test_il_livello_e_il_massimo_delle_fonti(pronto):
    await piani.concedi("server", 100, piani.PREMIUM, "mensile", giorni=30)
    assert await piani.livello_server(100) == piani.PREMIUM
    await piani.concedi("server", 100, piani.ULTRA, "manuale", giorni=None)  # a vita
    assert await piani.livello_server(100) == piani.ULTRA
    await piani.concedi("utente", 5, piani.VIP, "patreon", riferimento="m1")
    assert await piani.livello_utente(5) == piani.VIP
    assert await piani.revoca("utente", 5, "patreon") == 1
    assert await piani.livello_utente(5) == piani.GRATUITO


async def test_concessione_scaduta_non_vale(pronto):
    await piani.concedi("server", 100, piani.PREMIUM, "mensile", giorni=1)
    await pronto.execute("UPDATE piani_concessioni SET scade_il = now() - interval '1 minute'")
    assert await piani.livello_server(100) == piani.GRATUITO


async def test_boost_di_uno_dei_server_dell_owner(pronto, monkeypatch):
    from datetime import datetime, timezone

    from core import premium as premium_module

    monkeypatch.setattr(premium_module, "config", SimpleNamespace(PREMIUM_ALPHA_UNLOCK_ALL=False, MAIN_GUILD_ID=999, PREMIUM_BOOST_GUILD_IDS="998, 997"))
    booster = SimpleNamespace(premium_since=datetime.now(timezone.utc))
    secondo = _Guild(998, membri={42: booster})
    mio = _Guild(100, owner_id=42)
    assert await piani.livello_server(100, _Bot(_Guild(999), secondo, mio)) == piani.PREMIUM
    assert piani.utente_fa_boost(42, _Bot(_Guild(999), _Guild(998)), SimpleNamespace(MAIN_GUILD_ID=999, PREMIUM_BOOST_GUILD_IDS="")) is False


async def test_chiave_propria_da_vip_a_se_e_al_server(pronto):
    await chiavi.salva("utente", 5, "gemini", "chiave-segreta-1234", messa_da=5)
    assert await piani.livello_utente(5) == piani.VIP
    bot = _Bot(_Guild(100, owner_id=5))
    assert await piani.livello_server(100, bot) == piani.VIP  # il suo server
    assert await piani.livello_server(100) == piani.GRATUITO  # senza sapere chi è il proprietario
    assert await piani.livello_utente(6) == piani.GRATUITO  # un altro non ne approfitta
    await chiavi.salva("server", 100, "groq", "altra-chiave-5678", messa_da=7)
    assert await piani.livello_server(100) == piani.VIP


async def test_chiave_cifrata_mai_in_chiaro_e_si_toglie(pronto):
    await chiavi.salva("server", 100, "gemini", "chiave-segreta-1234", messa_da=7)
    grezzo = await pronto.fetchval("SELECT chiave_cifrata FROM ai_chiavi_proprie")
    assert "chiave-segreta-1234" not in grezzo
    assert await chiavi.chiave_per("gemini", guild_id=100) == "chiave-segreta-1234"
    assert await chiavi.chiave_per("gemini", guild_id=101) is None  # solo per chi l'ha messa
    assert await chiavi.chiave_per("groq", guild_id=100) is None
    assert await chiavi.servizi_con_chiave("server", 100) == ["gemini"]
    # la riga copiata su un altro server non si decifra (dato associato)
    await pronto.execute("UPDATE ai_chiavi_proprie SET ambito_id = 101")
    assert await chiavi.chiave_per("gemini", guild_id=101) is None
    await pronto.execute("UPDATE ai_chiavi_proprie SET ambito_id = 100")
    assert await chiavi.togli("server", 100, "gemini") == 1
    assert await chiavi.chiave_per("gemini", guild_id=100) is None
    assert await piani.livello_server(100) == piani.GRATUITO


async def test_chiave_utente_batte_chiave_server(pronto):
    await chiavi.salva("server", 100, "gemini", "chiave-del-server", messa_da=7)
    await chiavi.salva("utente", 5, "gemini", "chiave-della-persona", messa_da=5)
    assert await chiavi.chiave_per("gemini", guild_id=100, user_id=5) == "chiave-della-persona"
    assert await chiavi.chiave_per("gemini", guild_id=100, user_id=6) == "chiave-del-server"


async def test_chiave_rifiuta_valori_strani_e_cifratura_assente(pronto, monkeypatch):
    for chiave in ("corta", "con spazi dentro ok", "x" * 500):
        with pytest.raises(chiavi.ChiaveNonValida):
            await chiavi.salva("server", 100, "gemini", chiave, 1)
    with pytest.raises(chiavi.ChiaveNonValida):
        await chiavi.salva("server", 100, "../x", "chiave-valida-12", 1)
    monkeypatch.setattr(chiavi, "_chiave_cifratura", lambda: (_ for _ in ()).throw(chiavi.CifraturaNonConfigurata("x")))
    with pytest.raises(chiavi.CifraturaNonConfigurata):
        await chiavi.salva("server", 100, "gemini", "chiave-valida-12", 1)
    assert await pronto.fetchval("SELECT count(*) FROM ai_chiavi_proprie") == 0


async def test_limiti_per_livello_scelti_dall_owner(pronto):
    assert await piani.limite_di("backup_copie", piani.GRATUITO) == 10  # predefinito del codice
    await piani.imposta_limite("backup_copie", piani.GRATUITO, 2)
    await piani.imposta_limite("backup_copie", piani.PREMIUM, 20)
    await piani.imposta_limite("backup_copie", piani.VIP, 100)
    assert await piani.limite_server(100, "backup_copie") == 2
    await piani.concedi("server", 100, piani.PREMIUM, "annuale", giorni=365)
    assert await piani.limite_server(100, "backup_copie") == 20
    await piani.concedi("server", 100, piani.VIP, "a_vita", giorni=None)
    assert await piani.limite_server(100, "backup_copie") == 100
    await piani.imposta_limite("backup_copie", piani.VIP, None)  # torna il predefinito
    assert await piani.limite_server(100, "backup_copie") == 10
    tab = dict((c, v) for c, _, v in await piani.tabella_limiti())
    assert tab["backup_copie"] == [2, 20, 10, 10]


async def test_limiti_rifiutano_valori_fuori_misura(pronto):
    for args in (("sconosciuto", piani.VIP, 1), ("backup_copie", "oro", 1), ("backup_copie", piani.VIP, -1),
                 ("backup_copie", piani.VIP, piani.MAX_VALORE + 1), ("backup_copie", piani.VIP, True)):
        with pytest.raises(piani.PianoNonValido):
            await piani.imposta_limite(*args)


async def test_prezzi_e_sconti_scelti_dall_owner(pronto):
    assert await piani.testo_listino() == "I prezzi non sono ancora stati decisi."
    await piani.imposta_prezzo(piani.PREMIUM, "mensile", 499)
    await piani.imposta_prezzo(piani.VIP, "annuale", 20000)
    await piani.imposta_sconto("lancio", 20, livello=piani.PREMIUM, giorni=7)
    righe = {(l, p): (pieno, finale) for l, p, pieno, finale, _ in await piani.listino()}
    assert righe[(piani.PREMIUM, "mensile")] == (499, 400)  # 399,2 arrotondato per eccesso
    assert righe[(piani.VIP, "annuale")] == (20000, 20000)  # lo sconto è solo per Premium
    testo = await piani.testo_listino()
    assert "4,99" in testo and "non si fa dal bot" in testo
    await pronto.execute("UPDATE piani_sconti SET valido_fino = now() - interval '1 day'")
    assert {(l, p): f for l, p, _, f, _ in await piani.listino()}[(piani.PREMIUM, "mensile")] == 499
    await piani.imposta_sconto("lancio", None)
    assert await pronto.fetchval("SELECT count(*) FROM piani_sconti") == 0
    for chiamata in (piani.imposta_prezzo("gratuito", "mensile", 1), piani.imposta_prezzo(piani.VIP, "mensile", -5),
                     piani.imposta_sconto("x", 101)):
        with pytest.raises(piani.PianoNonValido):
            await chiamata


def test_prezzo_scontato_non_scende_sotto_zero():
    assert piani.prezzo_scontato(1000, [50, 50]) == 250
    assert piani.prezzo_scontato(1000, [100]) == 0
    assert piani.prezzo_scontato(1000, []) == 1000


async def _t(chiave, **kw):
    return f"{chiave}:{sorted(kw.items())}"


async def test_comando_chiave_non_mostra_mai_la_chiave(pronto):
    from core.piani_comandi import esegui_chiave

    ris = await esegui_chiave("imposta", ambito="server", ambito_id=100, servizio="gemini", chiave="chiave-segreta-1234", utente_id=7, t=_t)
    assert ris.startswith("piani_chiave_salvata") and "chiave-segreta" not in ris
    assert "gemini" in await esegui_chiave("elenco", ambito="server", ambito_id=100, servizio=None, chiave=None, utente_id=7, t=_t)
    assert (await esegui_chiave("imposta", ambito="server", ambito_id=100, servizio="Bad Name", chiave="chiave-segreta-1234", utente_id=7, t=_t)).startswith("piani_chiave_non_valida")
    assert "('n', 1)" in await esegui_chiave("togli", ambito="server", ambito_id=100, servizio=None, chiave=None, utente_id=7, t=_t)


async def test_comando_owner_piani(pronto):
    from core.piani_comandi import esegui_owner

    base = dict(livello=None, periodo=None, chiave=None, valore=None, utente_id=None, server_id=None, owner_id=1)
    assert "Limite" in await esegui_owner("limite", **{**base, "livello": "vip", "chiave": "backup_copie", "valore": 50})
    assert await piani.limite_di("backup_copie", "vip") == 50
    assert "non valido" in await esegui_owner("limite", **{**base, "livello": "vip", "chiave": "backup_copie", "valore": 2_000_000})
    assert "Ultra" in await esegui_owner("concedi", **{**base, "livello": "ultra", "periodo": "mensile", "server_id": 100})
    assert await piani.livello_server(100) == "ultra"
    assert "tolte: 1" in await esegui_owner("revoca", **{**base, "server_id": 100})
    assert await piani.livello_server(100) == "gratuito"
    assert "4,99" in await esegui_owner("prezzo", **{**base, "livello": "premium", "periodo": "mensile", "valore": 499})
    assert "4,99" in await esegui_owner("mostra", **base)


async def test_i_moduli_leggono_il_limite_dal_livello(pronto):
    """Le copie di backup e i pannelli ticket seguono il limite del livello (non più la costante)."""
    from core.repositories.backup_struttura_repo import BackupStrutturaRepository
    from core.repositories.ticket_form_repo import TroppiPannelli, ticket_form_repo
    import core.database as database_module

    repo = BackupStrutturaRepository(lambda: pronto) if "pool_provider" in BackupStrutturaRepository.__init__.__code__.co_varnames else None
    assert repo is not None
    await piani.imposta_limite("backup_copie", piani.GRATUITO, 2)
    assert await repo.salva_struttura(100, "a", 1, {}) is not None
    assert await repo.salva_struttura(100, "b", 1, {}) is not None
    assert await repo.salva_struttura(100, "c", 1, {}) is None  # gratuito: 2 copie
    await piani.concedi("server", 100, piani.PREMIUM, "mensile", giorni=30)
    await piani.imposta_limite("backup_copie", piani.PREMIUM, 3)
    assert await repo.salva_struttura(100, "c", 1, {}) is not None
    assert await repo.salva_struttura(100, "d", 1, {}) is None
    assert len(await repo.lista_strutture(100)) == 3
    assert database_module.db is not None and TroppiPannelli and ticket_form_repo
