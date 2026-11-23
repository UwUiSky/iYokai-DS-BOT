"""
tests/test_music_paese.py
=========================
Catalogo MUS (issue #126) giro r7mus: MUS-015, paese delle ricerche (D111, D115).
"""

from types import SimpleNamespace

import pytest

from core import music_paese_logic as pl
from core import music_sources as fonti


@pytest.fixture(autouse=True)
def _globale_spento():
    pl.imposta_paese_globale(None)
    yield
    pl.imposta_paese_globale(None)


def _traccia(plugin=None, info=None):
    return SimpleNamespace(raw_data={"pluginInfo": plugin or {}, "info": info or {}})


def test_paese_valido():
    assert pl.paese_valido(" it ") == "IT" and pl.paese_valido("TR") == "TR"
    for male in ("", "I", "ITA", "1T", "i ", "à", "İT", None, 5, "--", "I T"):
        assert pl.paese_valido(male) is None, male


def test_di_base_nessun_limite_e_il_server_vince_sul_globale():
    assert pl.paese_effettivo(None) is None and pl.paese_effettivo("") is None
    pl.imposta_paese_globale("us")
    assert pl.paese_globale() == "US" and pl.paese_effettivo(None) == "US"
    assert pl.paese_effettivo("tr") == "TR"
    assert pl.paese_effettivo("xyz") == "US"  # un valore storto non vale
    pl.imposta_paese_globale("non valido")
    assert pl.paese_globale() is None


def test_senza_dato_il_brano_passa_con_dato_si_decide():
    assert not pl.non_disponibile(_traccia(), "TR")                      # la fonte non lo dice (YouTube)
    assert not pl.non_disponibile(_traccia({"availableMarkets": ["IT", "TR"]}), "TR")
    assert pl.non_disponibile(_traccia({"availableMarkets": ["IT", "US"]}), "TR")
    assert pl.non_disponibile(_traccia({"available_countries": ["it"]}), "TR")
    assert pl.non_disponibile(_traccia(info={"markets": ["DE"]}), "TR")
    assert not pl.non_disponibile(_traccia({"availableMarkets": ["IT"]}), None)   # nessun filtro
    assert not pl.non_disponibile(_traccia({"availableMarkets": []}), "TR")       # elenco vuoto = non lo dice
    assert not pl.non_disponibile(_traccia({"availableMarkets": "IT"}), "TR")     # forma storta
    assert not pl.non_disponibile(SimpleNamespace(), "TR")                        # oggetto senza dati


def test_togli_non_disponibili_conta_gli_scartati():
    t1, t2, t3 = _traccia({"availableMarkets": ["TR"]}), _traccia({"availableMarkets": ["IT"]}), _traccia()
    tenute, scartate = pl.togli_non_disponibili([t1, t2, t3], "TR")
    assert tenute == [t1, t3] and scartate == 1
    assert pl.togli_non_disponibili([t1, t2], None) == ([t1, t2], 0)


# ----------------------------- Deezer -----------------------------
def test_deezer_legge_i_paesi_del_brano_se_ci_sono():
    uno = fonti.interpreta_deezer("brano", {"title": "T", "artist": {"name": "A"}, "available_countries": ["IT", "tr", 5, "xyz"]})
    assert uno[0].paesi == ("IT", "TR")
    assert fonti.interpreta_deezer("brano", {"title": "T"})[0].paesi == ()
    assert fonti.Metadato("T", "A").paesi == ()


def test_deezer_tiene_i_brani_di_cui_non_sa_nulla():
    ms = [fonti.Metadato("a", "x", paesi=("IT",)), fonti.Metadato("b", "x", paesi=("TR",)), fonti.Metadato("c", "x")]
    assert [m.titolo for m in fonti.filtra_metadati_per_paese(ms, "TR")] == ["b", "c"]
    assert fonti.filtra_metadati_per_paese(ms, None) == ms


# ----------------------------- impostazione del server -----------------------------
from cogs.music.settings import MusicSettingsCog  # noqa: E402
from cogs.utility import config_history as storia  # noqa: E402
from core import config_impostazioni as ci  # noqa: E402
from core.music_settings_logic import (  # noqa: E402
    SETTING_SEARCH_COUNTRY,
    MusicSettings,
    load_music_settings,
    summary_lines,
)


class _Db:
    def __init__(self, valori=None):
        self.valori = dict(valori or {})

    async def get_guild_setting(self, guild_id, chiave, default=None):
        return self.valori.get(chiave, default)

    async def set_guild_setting(self, guild_id, chiave, valore, changed_by=None):
        if valore is None:
            self.valori.pop(chiave, None)
        else:
            self.valori[chiave] = valore


def test_la_chiave_e_nello_schema_e_nella_scheda_del_pannello():
    assert SETTING_SEARCH_COUNTRY == "music_search_country"
    tipo = storia.SETTINGS_SCHEMA[SETTING_SEARCH_COUNTRY]
    controllo, _ = storia.CONTROLLI_PER_TIPO[tipo]
    assert controllo("TR") and controllo("it")
    assert not controllo("ITA") and not controllo("1") and not controllo(5) and not controllo("")
    assert any(c.chiave == SETTING_SEARCH_COUNTRY for c in ci.SCHEDE["music"])


@pytest.mark.asyncio
async def test_lettura_del_paese_del_server():
    assert (await load_music_settings(_Db(), 1)).search_country == ""
    assert (await load_music_settings(_Db({SETTING_SEARCH_COUNTRY: "tr"}), 1)).search_country == "TR"
    assert (await load_music_settings(_Db({SETTING_SEARCH_COUNTRY: "Turchia"}), 1)).search_country == ""
    assert (await load_music_settings(_Db({SETTING_SEARCH_COUNTRY: 5}), 1)).search_country == ""


def test_il_riepilogo_dice_il_paese():
    assert "TR" in "\n".join(summary_lines(MusicSettings(search_country="TR")))
    assert "tutto il mondo" in "\n".join(summary_lines(MusicSettings()))


class _Risposta:
    def __init__(self):
        self.inviati = []

    async def send_message(self, testo=None, **kw):
        self.inviati.append(testo)

    async def defer(self, **kw):
        pass


@pytest.mark.asyncio
async def test_il_comando_salva_rifiuta_e_toglie_il_paese(monkeypatch):
    import cogs.music.settings as modulo

    db = _Db()
    monkeypatch.setattr(modulo, "db", db)
    cog = MusicSettingsCog(bot=None)

    def interazione():
        i = SimpleNamespace(guild=SimpleNamespace(id=900), user=SimpleNamespace(id=5), locale=None,
                            guild_id=900, response=_Risposta(), followup=_Risposta())
        i.followup.send = i.followup.send_message
        return i

    await cog.impostazioni.callback(cog, interazione(), paese="tr")
    assert db.valori[SETTING_SEARCH_COUNTRY] == "TR"
    storto = interazione()
    await cog.impostazioni.callback(cog, storto, paese="x1")
    assert db.valori[SETTING_SEARCH_COUNTRY] == "TR" and "codice" in storto.response.inviati[0].lower()
    await cog.impostazioni.callback(cog, interazione(), paese="-")
    assert SETTING_SEARCH_COUNTRY not in db.valori


# ----------------------------- /music play con il filtro -----------------------------
from unittest.mock import AsyncMock, patch  # noqa: E402

import cogs.music.player as player_module  # noqa: E402
from cogs.music.player import MusicCog  # noqa: E402
from tests.test_music_f2 import (  # noqa: E402
    MAIN_KEY, _CanaleDelWorker, _FlottaDi, _GuildDelWorker, _Gestore, _Interazione,
)


def _con_paese(monkeypatch, paese):
    async def get(guild_id, chiave, default=None):
        return paese if (chiave == SETTING_SEARCH_COUNTRY and paese) else default

    monkeypatch.setattr(player_module, "db", SimpleNamespace(
        is_module_active_for_guild=AsyncMock(return_value=True), get_guild_setting=get,
    ))


def _scena():
    canale = _CanaleDelWorker(11)
    worker = SimpleNamespace(worker_index=2, get_guild=lambda gid: _GuildDelWorker(canale))
    gestore = _Gestore()
    nodo = object()
    gestore.nodi = {MAIN_KEY: nodo, "w2": nodo}
    cog = MusicCog(bot=SimpleNamespace(music_fleet=_FlottaDi(worker), music_nodes=gestore))
    return cog, canale, nodo


def _t(titolo, mercati=None):
    plugin = {"availableMarkets": mercati} if mercati else {}
    return SimpleNamespace(title=titolo, length=1000, raw_data={"pluginInfo": plugin, "info": {}}, extras=None)


async def _play(cog, nodo, risultati, query="qualcosa"):
    with patch.object(cog, "_cerca", new=AsyncMock(return_value=(risultati, nodo))) as cerca:
        i = _Interazione()
        await cog.play.callback(cog, i, query=query)
    return i, cerca


@pytest.mark.asyncio
async def test_il_server_con_paese_scarta_i_brani_non_ascoltabili(monkeypatch):
    _con_paese(monkeypatch, "TR")
    cog, canale, nodo = _scena()
    i, cerca = await _play(cog, nodo, [_t("Bloccato", ["IT"]), _t("Libero", ["TR", "IT"])])
    assert cerca.await_args.kwargs["paese"] == "TR"  # la ricerca sa il paese (per Deezer)
    assert canale.cls is not None  # il bot e' entrato
    messaggio = " ".join(str(m) for m in i.followup.inviati)
    assert "Libero" in messaggio and "Bloccato" not in messaggio


@pytest.mark.asyncio
async def test_se_nessun_brano_e_ascoltabile_lo_dice_e_non_entra(monkeypatch):
    _con_paese(monkeypatch, "TR")
    cog, canale, nodo = _scena()
    i, _ = await _play(cog, nodo, [_t("Bloccato", ["IT"])])
    assert canale.cls is None
    assert "TR" in i.followup.inviati[0] and "non è disponibile" in i.followup.inviati[0]


@pytest.mark.asyncio
async def test_senza_paese_nessun_limite_e_senza_dato_il_brano_passa(monkeypatch):
    _con_paese(monkeypatch, None)
    cog, canale, nodo = _scena()
    i, cerca = await _play(cog, nodo, [_t("Bloccato", ["IT"])])
    assert canale.cls is not None and "paese" not in cerca.await_args.kwargs
    _con_paese(monkeypatch, "TR")
    cog, canale, nodo = _scena()
    await _play(cog, nodo, [_t("Senza dato")])  # YouTube non dice i paesi
    assert canale.cls is not None


@pytest.mark.asyncio
async def test_il_paese_globale_dell_owner_vale_per_chi_non_ha_scelto(monkeypatch):
    _con_paese(monkeypatch, None)
    pl.imposta_paese_globale("TR")
    cog, canale, nodo = _scena()
    i, cerca = await _play(cog, nodo, [_t("Bloccato", ["IT"])])
    assert canale.cls is None and cerca.await_args.kwargs["paese"] == "TR"
    _con_paese(monkeypatch, "IT")  # il server sceglie il suo: vince
    cog, canale, nodo = _scena()
    await _play(cog, nodo, [_t("Bloccato", ["IT"])])
    assert canale.cls is not None


# ----------------------------- /owner radio paese -----------------------------
from cogs.music import paese as paese_mod  # noqa: E402
from core.repositories.music_cartella_repo import MusicCartellaRepository  # noqa: E402


class _Inter:
    def __init__(self, user_id):
        self.user, self.locale, self.guild = SimpleNamespace(id=user_id), None, None
        self.response = SimpleNamespace(send_message=AsyncMock(), defer=AsyncMock())


@pytest.mark.asyncio
async def test_owner_paese_imposta_mostra_e_toglie(clean_db, monkeypatch):
    repo = MusicCartellaRepository(lambda: clean_db)
    monkeypatch.setattr(paese_mod, "music_cartella_repo", repo)
    monkeypatch.setattr(paese_mod, "config", SimpleNamespace(OWNER_ID=1))
    cog = paese_mod.MusicPaeseCog(SimpleNamespace())

    estraneo = _Inter(2)
    await cog.paese.callback(cog, estraneo, "tr")
    assert pl.paese_globale() is None and await repo.leggi_impostazione("paese_globale") is None

    await cog.paese.callback(cog, _Inter(1), "tr")
    assert pl.paese_globale() == "TR" and await repo.leggi_impostazione("paese_globale") == "TR"
    storto = _Inter(1)
    await cog.paese.callback(cog, storto, "x1")
    assert pl.paese_globale() == "TR" and "non è valido" in storto.response.send_message.await_args.args[0]
    mostra = _Inter(1)
    await cog.paese.callback(cog, mostra, None)
    assert "TR" in mostra.response.send_message.await_args.args[0]

    pl.imposta_paese_globale(None)
    await paese_mod.carica_paese_globale()  # come a un riavvio
    assert pl.paese_globale() == "TR"
    await cog.paese.callback(cog, _Inter(1), "-")
    assert pl.paese_globale() is None and await repo.leggi_impostazione("paese_globale") is None


@pytest.mark.asyncio
async def test_deezer_risolve_solo_i_brani_del_paese(monkeypatch):
    async def metadati(tipo, id_):
        return [fonti.Metadato("a", "x", paesi=("IT",)), fonti.Metadato("b", "x", paesi=("TR",))]

    async def senza_circuito(fonte, esegui):
        return await esegui()

    visti = []

    async def risolvi(lista, esegui):
        visti.extend(m.titolo for m in lista)
        return list(lista)

    monkeypatch.setattr(fonti, "metadati_deezer", metadati)
    monkeypatch.setattr(fonti, "cerca_link", senza_circuito)
    monkeypatch.setattr(fonti, "_risolvi_elenco", risolvi)
    await fonti.risolvi_deezer("album", "1", None, "TR")
    assert visti == ["b"]
    visti.clear()
    await fonti.risolvi_deezer("album", "1", None)
    assert visti == ["a", "b"]
