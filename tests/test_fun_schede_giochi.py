"""B9 di #131 (D70): /web scheda, servizi esterni con cache, chiavi mai nei log. Nessuna rete vera."""
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import discord
import pytest

from cogs.fun import schede_giochi as cs
from core import safe_http
from core import schede_giochi_logic as sl
from core.repositories.cache_esterna_repo import cache_esterna_repo as repo
from tests.support.discord_fakes import fake_guild, fake_interaction

SEGRETO = "chiave-segretissima-123"


class _C:
    def __init__(self, value):
        self.value = value
        self.name = value


class FakeHttp:
    """Sostituisce sl._http: risponde per sottostringa dell'indirizzo e ricorda le chiamate."""

    def __init__(self, risposte):
        self.risposte, self.chiamate = risposte, []

    async def __call__(self, url, **kw):
        self.chiamate.append((url, kw))
        for pezzo, risposta in self.risposte.items():
            if pezzo in url:
                return risposta if risposta is None or isinstance(risposta, str) else json.dumps(risposta)
        return None


@pytest.fixture(autouse=True)
def _senza_attese(monkeypatch):
    monkeypatch.setattr(sl, "_ritmo", AsyncMock())
    monkeypatch.setattr(sl, "_nomi_pokemon", (0.0, []))
    sl._carte_hs.clear()
    sl._token_osu.update(valore=None, scade=0.0)


class CacheMemoria:
    def __init__(self):
        self.d = {}

    async def leggi(self, chiave):
        return self.d.get(chiave)

    async def salva(self, chiave, dati, secondi):
        self.d[chiave] = dati


# --- configurazione -----------------------------------------------------------

def test_servizi_accesi_solo_con_chiave_e_interruttore(tmp_path):
    assert sl.servizio_acceso("pokemon", {}) and sl.servizio_acceso("magic", {})
    assert not sl.servizio_acceso("osu", {}) and not sl.servizio_acceso("fortnite", {"GIOCHI_FORTNITE_KEY": " "})
    assert sl.servizio_acceso("fortnite", {"GIOCHI_FORTNITE_KEY": "k"})
    assert not sl.servizio_acceso("anime", {"GIOCHI_ANILIST_ATTIVO": "no"}) and not sl.servizio_acceso("manga", {"GIOCHI_ANILIST_ATTIVO": "NO"})
    f = tmp_path / "g.env"
    f.write_text("GIOCHI_OSU_KEY=1:abc\nALTRA=1\nGIOCHI_SCRYFALL_ATTIVO=no\n")
    e = sl.env_con_file({"GIOCHI_OSU_KEY": ""}, f)
    assert e["GIOCHI_OSU_KEY"] == "1:abc" and "ALTRA" not in e
    assert not sl.servizio_acceso("magic", e) and sl.servizio_acceso("osu", e)
    assert sl.env_con_file({}, tmp_path / "manca.env") == {}


# --- Pokémon ------------------------------------------------------------------

def test_debolezze_charizard():
    d = sl.debolezze(["fire", "flying"])
    assert d[4.0] == ["rock"] and set(d[2.0]) == {"water", "electric"} and set(d[0.25]) == {"grass", "bug"} and d[0.0] == ["ground"]
    assert "fighting" in d[0.5] and sl.debolezze(["normal"]) == {2.0: ["fighting"], 0.0: ["ghost"]}
    assert sl.debolezze(["sconosciuto"]) == {}
    assert "×4" in cs.testo_debolezze(["fire", "flying"], "it") and "roccia" in cs.testo_debolezze(["fire", "flying"], "it")
    assert "Rock" in cs.testo_debolezze(["fire", "flying"], "en-US")


POKE = {
    "id": 6, "name": "charizard", "height": 17, "weight": 905, "species": {"name": "charizard"},
    "types": [{"slot": 2, "type": {"name": "flying"}}, {"slot": 1, "type": {"name": "fire"}}],
    "abilities": [{"ability": {"name": "solar-power"}}], "stats": [{"stat": {"name": "hp"}, "base_stat": 78}],
    "sprites": {"other": {"official-artwork": {"front_default": "https://raw.githubusercontent.com/PokeAPI/sprites/a.png"}}},
}
SPECIE = {"names": [{"language": {"name": "it"}, "name": "Charizard"}], "flavor_text_entries": [
    {"language": {"name": "en"}, "flavor_text": "Flame\nbreath"}, {"language": {"name": "it"}, "flavor_text": "Sputa\ffuoco."}]}


async def test_pokemon_scheda_e_nome_simile(monkeypatch):
    http = FakeHttp({"pokemon-species?limit": {"results": [{"name": "charizard"}, {"name": "pikachu"}]},
                     "/pokemon-species/charizard": SPECIE, "/pokemon/charizard": POKE})
    monkeypatch.setattr(sl, "_http", http)
    d = await sl.cerca_pokemon("Charizard", "it")
    assert d["titolo"] == "#6 Charizard" and d["tipi"] == ["fire", "flying"] and d["descrizione"] == "Sputa fuoco."
    assert d["miniatura"].startswith("https://raw.githubusercontent.com/") and any(c == "scheda_campo_altezza_peso" for c, _ in d["campi"])
    d2 = await sl.cerca_pokemon("charzard", "en-US")  # errore di battitura: si cerca il più simile
    assert d2["titolo"] == "#6 Charizard" and d2["descrizione"] == "Flame breath"
    assert await sl.cerca_pokemon("zzzzzz", "it") is None and await sl.cerca_pokemon("!!", "it") is None


async def test_cache_evita_la_seconda_richiesta(monkeypatch):
    http = FakeHttp({"/pokemon-species/charizard": SPECIE, "/pokemon/charizard": POKE})
    monkeypatch.setattr(sl, "_http", http)
    cache = CacheMemoria()
    a = await sl.cerca("pokemon", "  Charizard ", "it", cache)
    n = len(http.chiamate)
    b = await sl.cerca("pokemon", "charizard", "it", cache)
    assert a == b and len(http.chiamate) == n
    await sl.cerca("pokemon", "charizard", "en-US", cache)  # un'altra lingua è un'altra scheda
    assert len(http.chiamate) > n
    assert await sl.cerca("sconosciuto", "x", "it", cache) is None and await sl.cerca("pokemon", "   ", "it", cache) is None


async def test_cache_su_database(clean_db, monkeypatch):
    import core.database as dm

    monkeypatch.setattr(dm.db, "_pool", clean_db)
    assert await repo.leggi("k") is None
    await repo.salva("k", {"a": [1, "è"]}, 60)
    assert await repo.leggi("k") == {"a": [1, "è"]}
    await repo.salva("k", {"b": 2}, 60)
    assert await repo.leggi("k") == {"b": 2}
    await repo.salva("scaduta", {"x": 1}, -5)
    assert await repo.leggi("scaduta") is None


async def test_risposta_non_leggibile_non_si_salva_e_non_scrive_il_testo(monkeypatch, caplog):
    monkeypatch.setattr(sl, "_http", FakeHttp({"pokeapi": f"non json {SEGRETO}"}))
    cache = CacheMemoria()
    with caplog.at_level(logging.WARNING):
        assert await sl.cerca("pokemon", "pikachu", "it", cache) is None
    assert cache.d == {} and SEGRETO not in caplog.text and "JSONDecodeError" in caplog.text


# --- AniList ------------------------------------------------------------------

async def test_anilist_testo_pulito_e_adulti(monkeypatch):
    media = {"data": {"Media": {"title": {"romaji": "Sousou no Frieren", "english": "Frieren"}, "description": "<p>Una <b>maga</b> &amp; il tempo.<br>" + "x" * 2000,
             "siteUrl": "https://anilist.co/anime/1", "coverImage": {"large": "https://s4.anilist.co/c.jpg"}, "format": "TV", "status": "FINISHED",
             "episodes": 28, "averageScore": 90, "genres": ["Fantasy"], "isAdult": False}}}
    http = FakeHttp({"graphql.anilist.co": media})
    monkeypatch.setattr(sl, "_http", http)
    d = await sl.cerca_anilist("frieren", "ANIME")
    assert d["titolo"] == "Frieren" and "<" not in d["descrizione"] and len(d["descrizione"]) <= 1000 and "maga & il tempo" in d["descrizione"]
    assert d["miniatura"] == "https://s4.anilist.co/c.jpg" and not d["adulti"]
    corpo = http.chiamate[0][1]["json_corpo"]
    assert corpo["variables"] == {"s": "frieren", "t": "ANIME"} and http.chiamate[0][1]["metodo"] == "POST"
    media["data"]["Media"].update(isAdult=True, siteUrl="http://evil.example/x", coverImage={"large": "https://evil.example/c.jpg"})
    d = await sl.cerca_anilist("x", "MANGA")
    assert d["adulti"] and d["url"] is None and d["miniatura"] is None
    monkeypatch.setattr(sl, "_http", FakeHttp({"anilist": {"data": {"Media": None}}}))
    assert await sl.cerca_anilist("niente", "ANIME") is None


# --- Magic e Hearthstone ---------------------------------------------------------

async def test_magic_immagine_intatta_e_intestazioni(monkeypatch):
    carta = {"object": "card", "name": "Lightning Bolt", "mana_cost": "{R}", "type_line": "Instant", "oracle_text": "Deals 3 damage.",
             "set_name": "Alpha", "rarity": "common", "scryfall_uri": "https://scryfall.com/card/x", "image_uris": {"normal": "https://cards.scryfall.io/normal/a.jpg"}}
    http = FakeHttp({"api.scryfall.com": carta})
    monkeypatch.setattr(sl, "_http", http)
    d = await sl.cerca_magic("lightning bolt")
    assert d["immagine"] == "https://cards.scryfall.io/normal/a.jpg" and d["url"].startswith("https://scryfall.com/")
    url, kw = http.chiamate[0]
    assert "fuzzy=lightning%20bolt" in url and "Accept" in kw["headers"] and "User-Agent" in kw["headers"]
    carta.pop("image_uris")
    carta["card_faces"] = [{"image_uris": {"normal": "https://cards.scryfall.io/normal/f.jpg"}, "oracle_text": "A"}]
    assert (await sl.cerca_magic("doppia"))["immagine"].endswith("f.jpg")
    carta["object"] = "error"
    assert await sl.cerca_magic("niente") is None


async def test_hearthstone_ricerca_e_cache_in_memoria(monkeypatch):
    carte = [{"id": "CS2_029", "name": "Palla di Fuoco", "text": "Infligge <b>6</b> danni.", "cost": 4, "type": "SPELL", "rarity": "FREE", "cardClass": "MAGE"},
             {"id": "EX1_116", "name": "Leeroy Jenkins", "text": "", "cost": 5, "attack": 6, "health": 2, "type": "MINION", "rarity": "LEGENDARY", "cardClass": "NEUTRAL"},
             {"id": "../x", "name": "Cattiva", "text": ""}]
    http = FakeHttp({"hearthstonejson": carte})
    monkeypatch.setattr(sl, "_http", http)
    d = await sl.cerca_hearthstone("palla di fuoco", "it")
    assert d["immagine"].endswith("/itIT/512x/CS2_029.png") and "6 danni" in dict(d["campi"])["scheda_campo_testo"]
    assert (await sl.cerca_hearthstone("leeroy", "it"))["titolo"] == "Leeroy Jenkins"
    assert dict((await sl.cerca_hearthstone("Leeroi Jenkins", "it"))["campi"])["scheda_campo_attacco_salute"] == "6/2"
    assert len(http.chiamate) == 1  # l'elenco si scarica una volta sola
    assert await sl.cerca_hearthstone("cattiva", "it") is None and await sl.cerca_hearthstone("zzzzzz", "it") is None


# --- osu! e Fortnite ----------------------------------------------------------------

async def test_osu_token_una_volta_e_chiave_non_nei_log(monkeypatch, caplog):
    monkeypatch.setenv("GIOCHI_OSU_KEY", f"123:{SEGRETO}")
    utente = {"id": 2, "username": "Cookiezi", "avatar_url": "https://a.ppy.sh/2", "country_code": "KR",
              "statistics": {"global_rank": 5, "pp": 14000.4, "hit_accuracy": 98.123, "play_count": 100, "level": {"current": 105}, "play_time": 7200}}
    http = FakeHttp({"oauth/token": {"access_token": "TOKEN-OSU", "expires_in": 86400}, "api/v2/users/": utente})
    monkeypatch.setattr(sl, "_http", http)
    d = await sl.cerca_osu("Cookiezi")
    await sl.cerca_osu("Cookiezi")
    assert d["titolo"] == "Cookiezi" and d["url"] == "https://osu.ppy.sh/users/2" and dict(d["campi"])["scheda_campo_ore"] == "2"
    assert sum("oauth/token" in u for u, _ in http.chiamate) == 1
    ultimo = http.chiamate[-1]
    assert ultimo[1]["headers"]["Authorization"] == "Bearer TOKEN-OSU" and "TOKEN-OSU" not in ultimo[0] and SEGRETO not in ultimo[0]
    assert http.chiamate[0][1]["json_corpo"]["client_id"] == 123
    assert SEGRETO not in json.dumps(d) and SEGRETO not in caplog.text
    sl._token_osu.update(valore=None, scade=0.0)
    monkeypatch.setenv("GIOCHI_OSU_KEY", "senza-due-punti")
    assert await sl.cerca_osu("x") is None


async def test_fortnite_statistiche(monkeypatch):
    monkeypatch.setenv("GIOCHI_FORTNITE_KEY", SEGRETO)
    risposta = {"data": {"account": {"name": "Ninja"}, "battlePass": {"level": 80}, "stats": {"all": {"overall": {"wins": 10, "kills": 99, "matches": 50, "kd": 2.5, "winRate": 20.0, "minutesPlayed": 600}}}}}
    http = FakeHttp({"fortnite-api.com": risposta})
    monkeypatch.setattr(sl, "_http", http)
    d = await sl.cerca_fortnite("Ninja")
    assert d["titolo"] == "Ninja" and dict(d["campi"])["scheda_campo_ore"] == "10"
    url, kw = http.chiamate[0]
    assert kw["headers"]["Authorization"] == SEGRETO and SEGRETO not in url
    risposta["data"]["stats"] = None  # profilo privato
    assert await sl.cerca_fortnite("Ninja") is None


# --- safe_richiesta -----------------------------------------------------------------

class _Risp:
    def __init__(self, stato, corpo=b""):
        self.status, self._c, self.charset = stato, corpo, "utf-8"
        self.content = SimpleNamespace(iter_chunked=self._chunks)

    async def _chunks(self, n):
        for i in range(0, len(self._c), n):
            yield self._c[i : i + n]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _sessione(monkeypatch, risposta=None, errore=None):
    visti = {}

    def richiesta(metodo, url, **kw):
        visti.update(metodo=metodo, url=str(url), **kw)
        if errore:
            raise errore
        return risposta

    sess = SimpleNamespace(request=richiesta)
    monkeypatch.setattr(safe_http, "_sessione_condivisa", AsyncMock(return_value=sess))
    return visti


async def test_safe_richiesta_regole(monkeypatch, caplog):
    assert await safe_http.safe_richiesta("http://127.0.0.1/x") is None  # indirizzo interno
    assert await safe_http.safe_richiesta("ftp://pokeapi.co/x") is None
    visti = _sessione(monkeypatch, _Risp(200, "ciao è".encode()))
    assert await safe_http.safe_richiesta("https://osu.ppy.sh/api", metodo="POST", headers={"Authorization": "Bearer X"}, json_corpo={"a": 1}) == "ciao è"
    assert visti["allow_redirects"] is False and visti["metodo"] == "POST" and visti["json"] == {"a": 1}
    _sessione(monkeypatch, _Risp(302))
    assert await safe_http.safe_richiesta("https://osu.ppy.sh/api") is None  # niente redirect: le credenziali non lo seguono
    _sessione(monkeypatch, _Risp(200, b"x" * 100))
    assert await safe_http.safe_richiesta("https://osu.ppy.sh/api", max_bytes=10) is None
    _sessione(monkeypatch, errore=aiohttp.ClientError(f"boom {SEGRETO}"))
    with caplog.at_level(logging.WARNING):
        assert await safe_http.safe_richiesta(f"https://osu.ppy.sh/api?key={SEGRETO}") is None
    assert SEGRETO not in caplog.text and "ClientError" in caplog.text


# --- comando ------------------------------------------------------------------------

def _it(nsfw=False):
    it = fake_interaction(guild=fake_guild(1))
    it.channel = MagicMock(spec=discord.TextChannel)
    it.channel.is_nsfw = MagicMock(return_value=nsfw)
    return it


async def test_comando_scheda_spento_non_trovata_adulti_e_bottone(monkeypatch, clean_db):
    import core.database as dm

    monkeypatch.setattr(dm.db, "_pool", clean_db)
    monkeypatch.delenv("GIOCHI_OSU_KEY", raising=False)
    cog = cs.SchedeGiochiCog(bot=None)
    it = _it()
    await cog.scheda.callback(cog, it, _C("osu"), "x")  # niente chiave: spento
    assert it.response.send_message.await_args.kwargs["ephemeral"] and not it.response.defer.await_count
    monkeypatch.setattr(cs.sl, "cerca", AsyncMock(return_value=None))
    it = _it()
    await cog.scheda.callback(cog, it, _C("pokemon"), "x")
    assert it.followup.send.await_args.kwargs["ephemeral"] is True
    adulto = sl._scheda("Titolo", "d", None, None, None, [("scheda_campo_voto", "9/100")], adulti=True)
    monkeypatch.setattr(cs.sl, "cerca", AsyncMock(return_value=adulto))
    it = _it(nsfw=False)
    await cog.scheda.callback(cog, it, _C("anime"), "x")
    assert "embed" not in it.followup.send.await_args.kwargs
    it = _it(nsfw=True)
    await cog.scheda.callback(cog, it, _C("anime"), "x")
    emb = it.followup.send.await_args.kwargs["embed"]
    assert emb.title == "Titolo" and emb.fields[0].value == "9/100" and emb.footer.text
    poke = sl._scheda("#6 Charizard", "d", None, "https://raw.githubusercontent.com/a.png", None, [("scheda_campo_tipi", "fire / flying")], tipi=["fire", "flying"])
    monkeypatch.setattr(cs.sl, "cerca", AsyncMock(return_value=poke))
    it = _it()
    await cog.scheda.callback(cog, it, _C("pokemon"), "charizard")
    vista = it.followup.send.await_args.kwargs["view"]
    clic = _it()
    clic.user.id = it.user.id
    await vista.debolezze.callback(clic)
    assert "roccia" in clic.response.send_message.await_args.args[0] or "Rock" in clic.response.send_message.await_args.args[0]
    altro = _it()
    altro.user.id = it.user.id + 1
    assert await vista.interaction_check(altro) is False


async def test_albero_scheda_in_web():
    from discord.ext import commands

    from tests.support.percorsi import percorsi_del_gruppo

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    await cs.setup(bot)
    assert "scheda" in percorsi_del_gruppo("web")
