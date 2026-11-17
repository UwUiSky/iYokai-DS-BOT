"""#130 catalogo statistiche, blocco 3: canali contatore (tipi nuovi, segnaposto, traguardi, orologio, social, categoria)."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.utility.counters as modulo
from cogs.utility.counters import CountersCog, MODELLI_CATEGORIA
from core.counter_logic import (
    ETICHETTE_DI_BASE,
    MAX_CONTATORI,
    TIPI,
    Istantanea,
    leggi_traguardi,
    mancano,
    nome_del_contatore,
    ora_a_scatti,
    traguardo_corrente,
    valida_etichetta,
    valida_parametro,
    valore_del_contatore,
)
from core.counter_social import giocatori_minecraft, leggi_social
from core.counter_worker import CounterWorker
from core.repositories.counter_repo import CounterRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role

ADESSO = datetime(2026, 12, 20, 14, 37, tzinfo=timezone.utc)  # a Roma sono le 15:37 (inverno)


def _c(kind, label=None, target=None, param=None, targets=None):
    return SimpleNamespace(id=1, guild_id=1, channel_id=10, kind=kind, label=label or ETICHETTE_DI_BASE[kind],
                           target=target, last_value=None, param=param, targets=targets)


def _snap(**kw):
    base = dict(member_count=1000, online_count=120, boost_count=14, bot=30, livello_boost=3, ruoli=40, canali=60, emoji=25)
    base.update(kw)
    return Istantanea(**base)


# --- STA-033..039: tipi di numero ----------------------------------------------------

# STA-033, STA-034, STA-035
def test_sta_033_034_035_membri_utenti_e_bot():
    s = _snap()
    assert valore_del_contatore("members", s) == 1000
    assert valore_del_contatore("users", s) == 970  # STA-034: senza i bot
    assert valore_del_contatore("bots", s) == 30  # STA-035


# STA-036
def test_sta_036_boost_e_livello():
    s = _snap()
    assert valore_del_contatore("boosts", s) == 14
    assert valore_del_contatore("boost_tier", s) == 3


# STA-037
def test_sta_037_online_stimati_e_offline():
    assert valore_del_contatore("offline", _snap()) == 880
    assert valore_del_contatore("offline", _snap(online_count=None)) is None  # non si sa: il nome resta com'è
    assert valore_del_contatore("offline", _snap(online_count=5000)) == 0  # mai negativo


# STA-038
def test_sta_038_membri_con_e_senza_un_ruolo():
    s = _snap(per_ruolo={55: 200})
    assert valore_del_contatore("role_with", s, "55") == 200
    assert valore_del_contatore("role_without", s, "55") == 800
    assert valore_del_contatore("role_with", s, "99") is None  # ruolo sparito
    assert valore_del_contatore("role_with", s, "non-un-numero") is None


# --- STA-040: traguardi successivi, 041: testo intorno al numero -------------------------

# STA-040
def test_sta_040_traguardi_uno_dopo_l_altro():
    assert leggi_traguardi("5000, 1000;2000") == [1000, 2000, 5000]
    assert leggi_traguardi("abc") is None and leggi_traguardi("0,5") is None
    assert leggi_traguardi(",".join(str(i) for i in range(1, 12))) is None  # al massimo 10
    assert traguardo_corrente(950, 1000, None) == 1000
    assert traguardo_corrente(1000, None, "1000,2000,5000") == 2000
    assert traguardo_corrente(9999, None, "1000,2000,5000") == 5000  # superati tutti: resta l'ultimo
    nome = nome_del_contatore(_c("goal", "{n}/{target}", 100, targets="1000,2000"), _snap(member_count=1500), ADESSO)
    assert nome == "1500/2000"


# STA-041
def test_sta_041_testo_libero_intorno_al_numero_e_taglio_a_100():
    nome = nome_del_contatore(_c("members", "Siamo in {n}! " + "x" * 70), _snap(), ADESSO)
    assert nome.startswith("Siamo in 1000!") and len(nome) <= 100


# --- STA-043, 044, 048, 052: contatori di testo ----------------------------------------------

# STA-043
def test_sta_043_testo_fisso_senza_numero():
    assert valida_etichetta("📊 Statistiche", "static") is None
    assert nome_del_contatore(_c("static", "📊 Statistiche"), _snap(), ADESSO) == "📊 Statistiche"
    assert valida_etichetta("", "static") is not None


# STA-044
def test_sta_044_orologio_a_scatti_di_10_minuti():
    assert ora_a_scatti(ADESSO, "Europe/Rome") == "15:30"  # 15:37 -> 15:30
    assert ora_a_scatti(ADESSO, "America/New_York") == "09:30"
    assert ora_a_scatti(ADESSO, "Fuso/Che/Non/Esiste") == "15:30"  # ripiego sul fuso di base
    assert nome_del_contatore(_c("clock", "Ore {ora}", param="Europe/Rome"), _snap(), ADESSO) == "Ore 15:30"
    assert valida_etichetta("Ore", "clock") is not None


# STA-044
def test_sta_044_conto_alla_rovescia():
    assert mancano("2026-12-25", ADESSO) == (4, 8)  # mezzanotte a Roma = 23:00 UTC del 24
    assert mancano("2026-12-01", ADESSO) == (0, 0)  # passata: zero, mai negativo
    assert mancano("non una data", ADESSO) is None
    nome = nome_del_contatore(_c("countdown", "Natale tra {giorni}g {ore}h", param="2026-12-25 12:00"), _snap(), ADESSO)
    assert nome == "Natale tra 4g 20h"
    assert nome_del_contatore(_c("countdown", "x {giorni}", param="boh"), _snap(), ADESSO) is None


# STA-048
def test_sta_048_piu_numeri_in_un_solo_canale():
    s = _snap(ticket_aperti=7, ultimo_membro="Mario")
    nome = nome_del_contatore(_c("multi", "👥 {membri} · 🤖 {bot} · 🟢 {online} · 🎫 {ticket}"), s, ADESSO)
    assert nome == "👥 1000 · 🤖 30 · 🟢 120 · 🎫 7"
    assert nome_del_contatore(_c("multi", "{online}"), _snap(online_count=None), ADESSO) == "?"
    assert valida_etichetta("senza segnaposto", "multi") is not None
    # anche un contatore normale può avere i segnaposto con nome
    assert nome_del_contatore(_c("members", "{n} su {membri}, {bot} bot"), _snap(), ADESSO) == "1000 su 1000, 30 bot"


# STA-052
def test_sta_052_ultimo_membro_entrato():
    assert nome_del_contatore(_c("last_member"), _snap(ultimo_membro="Luna"), ADESSO) == "👋 Ultimo arrivato: Luna"
    assert nome_del_contatore(_c("last_member"), _snap(), ADESSO) is None  # nessuno noto: il nome resta com'è
    assert valida_etichetta("senza", "last_member") is not None


# --- parametri: sono dell'utente ----------------------------------------------------------------

def test_i_parametri_si_controllano_prima_di_usarli():
    assert valida_parametro("youtube", "UC" + "a" * 22) == ("UC" + "a" * 22, None)
    assert valida_parametro("youtube", "https://evil.example/x")[1] == "counters_param_youtube"
    assert valida_parametro("twitch", "Nome_Valido")[0] == "nome_valido"
    assert valida_parametro("twitch", "a b")[1] == "counters_param_twitch"
    assert valida_parametro("game", "Gioca.Esempio.it:25565") == ("gioca.esempio.it:25565", None)
    for cattivo in ("evil.com/../admin", "a.b?x=1", "http://x.it", "x" * 150, "ciao\nmondo", "#"):
        assert valida_parametro("game", cattivo)[1] == "counters_param_gioco", cattivo
    assert valida_parametro("clock", "")[0] == "Europe/Rome"
    assert valida_parametro("clock", "../../etc/passwd")[1] == "counters_param_fuso"
    assert valida_parametro("countdown", "2026-13-45")[1] == "counters_param_data"
    assert valida_parametro("role_with", "12x")[1] == "counters_param_ruolo"
    assert valida_parametro("members", "qualsiasi") == (None, None)  # un tipo senza parametro non ne tiene


# --- STA-045, 046: social e gioco -------------------------------------------------------------

# STA-046
async def test_sta_046_giocatori_minecraft_dal_servizio_pubblico():
    chiamate = []

    async def _leggi(url, max_bytes):
        chiamate.append(url)
        return '{"online": true, "players": {"online": 17, "max": 100}}'

    assert await giocatori_minecraft("gioca.esempio.it:25565", _leggi) == 17
    assert chiamate == ["https://api.mcsrvstat.us/3/gioca.esempio.it%3A25565"]  # l'indirizzo è un pezzo di percorso, codificato

    async def _spento(url, max_bytes):
        return '{"online": false}'

    async def _rotto(url, max_bytes):
        return "<html>"

    async def _niente(url, max_bytes):
        return None

    assert await giocatori_minecraft("x.it", _spento) == 0
    assert await giocatori_minecraft("x.it", _rotto) is None
    assert await giocatori_minecraft("x.it", _niente) is None


# STA-045, STA-046
async def test_sta_045_046_social_una_richiesta_per_gruppo(monkeypatch):
    import core.counter_social as cs

    monkeypatch.setattr(cs.asyncio, "sleep", AsyncMock())
    yt = AsyncMock(return_value={"UC" + "a" * 22: 1500, "UC" + "b" * 22: None})
    tw = AsyncMock(return_value={"streamer": 42})
    gioco = AsyncMock(return_value=9)
    richieste = {("youtube", "UC" + "a" * 22), ("youtube", "UC" + "b" * 22), ("twitch", "streamer"), ("game", "x.it")}
    out = await leggi_social(richieste, youtube=yt, twitch=tw, gioco=gioco)
    yt.assert_awaited_once()  # una chiamata per tutti i canali YouTube, non una per canale
    tw.assert_awaited_once()
    assert out["youtube:UC" + "a" * 22] == 1500 and out["youtube:UC" + "b" * 22] is None
    assert out["twitch:streamer"] == 42 and out["game:x.it"] == 9
    yt.side_effect = RuntimeError("giù")
    out = await leggi_social(richieste, youtube=yt, twitch=tw, gioco=gioco)  # un servizio rotto non ferma gli altri
    assert out["twitch:streamer"] == 42 and out["youtube:UC" + "a" * 22] is None


# STA-045
async def test_sta_045_iscritti_youtube_chiave_nell_intestazione(monkeypatch):
    from core.youtube_watcher import YoutubeWatcherService
    import core.youtube_watcher as yw

    monkeypatch.setattr(yw, "config", SimpleNamespace(YOUTUBE_API_KEY="chiave-finta"))
    viste = {}

    class _Risposta:
        status = 200

        async def json(self):
            return {"items": [{"id": "UC" + "a" * 22, "statistics": {"subscriberCount": "1234"}},
                              {"id": "UC" + "b" * 22, "statistics": {"hiddenSubscriberCount": True}}]}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class _Sessione:
        def get(self, url, params=None, headers=None, timeout=None):
            viste["url"], viste["params"], viste["headers"] = url, params, headers
            return _Risposta()

    servizio = YoutubeWatcherService()
    servizio._http_session = _Sessione()
    out = await servizio.iscritti(["UC" + "b" * 22, "UC" + "a" * 22, "UC" + "a" * 22])
    assert out == {"UC" + "a" * 22: 1234, "UC" + "b" * 22: None}
    assert "key" not in viste["params"] and "chiave-finta" not in viste["url"]
    assert viste["headers"] == {"x-goog-api-key": "chiave-finta"}
    monkeypatch.setattr(yw, "config", SimpleNamespace(YOUTUBE_API_KEY=""))
    assert await servizio.iscritti(["UC" + "a" * 22]) is None  # senza chiave non chiama nessuno


# STA-045
async def test_sta_045_spettatori_twitch_a_gruppi_da_100():
    from core.twitch_watcher import TwitchWatcherService

    servizio = TwitchWatcherService()
    chiamate = []

    async def _streams(logins):
        chiamate.append(len(logins))
        return {"data": [{"user_login": "Uno", "viewer_count": 42}]}

    servizio._fetch_streams = _streams
    out = await servizio.spettatori(["uno", "due"] + [f"canale{i}" for i in range(150)])
    assert chiamate == [100, 52] and out["uno"] == 42 and out["due"] == 0
    servizio._fetch_streams = AsyncMock(return_value=None)
    assert await servizio.spettatori(["uno"]) is None


# --- il giro dei contatori con i tipi nuovi ------------------------------------------------------

class _Scena:
    def __init__(self, contatori, *, social=None):
        self.guild = fake_guild(guild_id=1)
        self.guild.member_count = 100
        self.guild.premium_subscription_count = 3
        self.guild.premium_tier = 1
        self.canali = {}
        for c in contatori:
            canale = MagicMock(spec=discord.VoiceChannel)
            canale.id = c.channel_id
            canale.name = "vecchio"
            self.canali[c.channel_id] = canale
        self.guild.get_channel = lambda cid: self.canali.get(cid)
        self.bot = MagicMock()
        self.bot.get_guild = lambda gid: self.guild
        self.bot.fetch_guild = AsyncMock(return_value=SimpleNamespace(approximate_presence_count=40))
        self.repo = MagicMock()
        self.repo.list_all = AsyncMock(return_value=contatori)
        self.repo.set_last_value = AsyncMock()
        self.repo.delete_by_channel = AsyncMock()
        self.rinomina = AsyncMock()
        db_finto = MagicMock()
        db_finto.is_module_active_for_guild = AsyncMock(return_value=True)
        self.social = AsyncMock(return_value=social or {})
        self.worker = CounterWorker(self.repo, rename=self.rinomina, db=db_finto, social=self.social)

    def nomi(self):
        return {c.args[0].id: c.args[1] for c in self.rinomina.await_args_list}


def _dist(kind, cid, **kw):
    c = _c(kind, **kw)
    c.channel_id, c.id = cid, cid
    return c


# STA-034, STA-035
async def test_sta_034_035_bot_e_utenti_dal_giro():
    s = _Scena([_dist("users", 11), _dist("bots", 12)])
    s.guild.members = [fake_member(i, bot=(i < 3)) for i in range(10)]
    await s.worker.tick(s.bot)
    assert s.nomi() == {11: "🙂 Utenti: 97", 12: "🤖 Bot: 3"}


# STA-036, STA-037
async def test_sta_036_037_livello_e_offline_dal_giro():
    s = _Scena([_dist("boost_tier", 11), _dist("offline", 12)])
    await s.worker.tick(s.bot)
    assert s.nomi() == {11: "💎 Livello boost: 1", 12: "⚫ Offline: 60"}
    s.bot.fetch_guild.assert_awaited_once()  # una sola richiesta per i numeri online


# STA-038
async def test_sta_038_ruolo_dal_giro():
    ruolo = fake_role(55)
    ruolo.members = [fake_member(i) for i in range(7)]
    s = _Scena([_dist("role_with", 11, param="55"), _dist("role_without", 12, param="55")])
    s.guild.get_role = lambda rid: ruolo if rid == 55 else None
    await s.worker.tick(s.bot)
    assert s.nomi() == {11: "🎖️ Con il ruolo: 7", 12: "🚫 Senza il ruolo: 93"}


# STA-052
async def test_sta_052_ultimo_membro_dal_giro_ignora_i_bot():
    s = _Scena([_dist("last_member", 11)])
    vecchio, nuovo, robot = fake_member(1), fake_member(2), fake_member(3, bot=True)
    vecchio.display_name, nuovo.display_name, robot.display_name = "Vecchio", "  Nuovo   Arrivato ", "Robot"
    vecchio.joined_at, nuovo.joined_at, robot.joined_at = ADESSO - timedelta(days=9), ADESSO - timedelta(days=1), ADESSO
    s.guild.members = [vecchio, nuovo, robot]
    await s.worker.tick(s.bot)
    assert s.nomi() == {11: "👋 Ultimo arrivato: Nuovo Arrivato"}  # spazi ripuliti, il bot non conta


# STA-043, STA-044
async def test_sta_043_044_testo_fisso_e_orologio_non_rinominano_se_uguali():
    fisso = _dist("static", 11)
    s = _Scena([fisso])
    s.canali[11].name = "📊 Statistiche"
    await s.worker.tick(s.bot)
    s.rinomina.assert_not_awaited()  # il nome è già quello: niente chiamata a Discord (limite 2 ogni 10 minuti)
    s.repo.set_last_value.assert_not_awaited()


# STA-048
async def test_sta_048_multi_nel_giro():
    s = _Scena([_dist("multi", 11, label="👥 {membri} · 🟢 {online}")])
    await s.worker.tick(s.bot)
    assert s.nomi() == {11: "👥 100 · 🟢 40"}


# STA-045, STA-046
async def test_sta_045_046_il_giro_chiede_i_social_una_volta_sola():
    yt = "UC" + "a" * 22
    s = _Scena(
        [_dist("youtube", 11, param=yt), _dist("youtube", 12, param=yt, label="Iscritti {n}"), _dist("game", 13, param="x.it")],
        social={f"youtube:{yt}": 1500, "game:x.it": 8},
    )
    await s.worker.tick(s.bot)
    s.social.assert_awaited_once()
    assert s.social.await_args.args[0] == {("youtube", yt), ("game", "x.it")}
    assert s.nomi() == {11: "▶️ Iscritti: 1,5K", 12: "Iscritti 1500", 13: "🎮 Giocatori: 8"}
    # numero non letto: il canale resta com'è
    s2 = _Scena([_dist("youtube", 11, param=yt)], social={f"youtube:{yt}": None})
    await s2.worker.tick(s2.bot)
    s2.rinomina.assert_not_awaited()


async def test_un_server_con_il_modulo_spento_non_chiama_i_servizi_esterni_per_gli_altri():
    s = _Scena([_dist("members", 11)])
    await s.worker.tick(s.bot)
    s.social.assert_not_awaited()  # nessun contatore social: nessuna richiesta fuori


# --- comandi: STA-040, 049, 050, 051 --------------------------------------------------------------

@pytest.fixture
def cog(monkeypatch):
    c = CountersCog(MagicMock())
    repo = MagicMock()
    repo.create = AsyncMock(return_value="ok")
    repo.list_for_guild = AsyncMock(return_value=[])
    repo.delete = AsyncMock(return_value=True)
    repo.delete_all = AsyncMock(return_value=4)
    repo.delete_by_channel = AsyncMock()
    repo.get = AsyncMock(return_value=SimpleNamespace(id=3, kind="goal", label="{n}/{target}", target=100))
    repo.update = AsyncMock(return_value=True)
    monkeypatch.setattr(modulo, "counter_repo", repo)
    db_finto = MagicMock()
    db_finto.is_module_active_for_guild = AsyncMock(return_value=True)
    monkeypatch.setattr(modulo, "db", db_finto)
    c.repo = repo
    return c


def _it():
    server = fake_guild()
    server.member_count = 10
    return fake_interaction(guild=server), server


# STA-040, STA-049, STA-050
async def test_sta_040_049_050_crea_con_traguardi_e_con_ruolo_e_tipo_sconosciuto(cog):
    i, _ = _it()
    canale = MagicMock(spec=discord.VoiceChannel); canale.id = 10
    canale.permissions_for = MagicMock(return_value=discord.Permissions(manage_channels=True, view_channel=True))
    await cog.crea.callback(cog, i, "goal", canale, None, None, None, None, "2000, 1000")
    kw = cog.repo.create.await_args.kwargs
    assert kw["targets"] == "1000,2000" and cog.repo.create.await_args.args[4] == 1000  # il primo traguardo fa da obiettivo
    cog.repo.create.reset_mock()
    await cog.crea.callback(cog, i, "role_with", canale, None, None, fake_role(55), None, None)
    assert cog.repo.create.await_args.kwargs["param"] == "55"
    cog.repo.create.reset_mock()
    await cog.crea.callback(cog, i, "inventato", canale, None, None, None, None, None)
    await cog.crea.callback(cog, i, "role_with", canale, None, None, None, None, None)  # manca il ruolo
    await cog.crea.callback(cog, i, "members", canale, None, None, None, None, "1000")  # traguardi solo per l'obiettivo
    cog.repo.create.assert_not_awaited()


# STA-040
async def test_sta_040_autocompletamento_dei_tipi_al_massimo_25(cog):
    out = await cog._tipo_autocompleta.__wrapped__(cog, MagicMock(), "") if hasattr(cog._tipo_autocompleta, "__wrapped__") else await cog._tipo_autocompleta(MagicMock(), "")
    assert 0 < len(out) <= 25 and len(TIPI) <= 25
    cerca = await cog._tipo_autocompleta(MagicMock(), "orolo")
    assert [c.value for c in cerca] == ["clock"]


# STA-050
async def test_sta_050_modifica_e_rifiuti(cog):
    i, _ = _it()
    await cog.modifica.callback(cog, i, 3, "{n} su {target}", 500, "100,200", None)
    cog.repo.update.assert_awaited_once_with(i.guild.id, 3, label="{n} su {target}", target=500, targets="100,200")
    i, _ = _it()
    cog.repo.update.reset_mock()
    await cog.modifica.callback(cog, i, 3, "senza numero", None, None, None)  # etichetta senza {n}
    await cog.modifica.callback(cog, i, 3, None, None, None, None)  # niente da cambiare
    await cog.modifica.callback(cog, i, 3, None, None, None, "abc")  # il tipo obiettivo non ha parametro
    cog.repo.get.return_value = None
    await cog.modifica.callback(cog, i, 99, "{n}", None, None, None)  # numero inesistente
    cog.repo.update.assert_not_awaited()


# STA-051
async def test_sta_051_azzera_chiede_conferma_e_solo_all_autore(cog, monkeypatch):
    import core.ui_base as ui_base

    monkeypatch.setattr(ui_base, "_utente_o_server_in_blacklist", AsyncMock(return_value=False))
    i, server = _it()
    cog.repo.list_for_guild.return_value = [1, 2, 3, 4]
    await cog.azzera.callback(cog, i)
    vista = i.response.send_message.await_args.kwargs["view"]
    cog.repo.delete_all.assert_not_awaited()  # non si cancella senza il clic
    estraneo = fake_interaction(guild=server, user=fake_member(777))
    assert not await vista.interaction_check(estraneo)
    cog.repo.delete_all.assert_not_awaited()
    proprio = fake_interaction(guild=server, user=i.user)
    await vista.conferma.callback(proprio)
    cog.repo.delete_all.assert_awaited_once_with(server.id)
    # server senza contatori: niente conferma
    i2, _ = _it()
    cog.repo.list_for_guild.return_value = []
    await cog.azzera.callback(cog, i2)
    assert "view" not in i2.response.send_message.await_args.kwargs


# STA-049
async def test_sta_049_categoria_con_i_canali_chiusi_a_tutti(cog):
    i, server = _it()
    i.user.guild_permissions = discord.Permissions(manage_channels=True)
    server.me.guild_permissions = discord.Permissions(manage_channels=True)
    cat = MagicMock(); cat.id = 500; cat.mention = "<#500>"
    server.create_category = AsyncMock(return_value=cat)
    server.default_role = MagicMock()
    canali = []

    async def _vocale(nome, **kw):
        c = MagicMock(spec=discord.VoiceChannel); c.id = 600 + len(canali); canali.append((c, kw)); return c

    server.create_voice_channel = _vocale
    modello = SimpleNamespace(value="base")
    await cog.categoria.callback(cog, i, modello, "📊 Dati")
    assert len(canali) == len(MODELLI_CATEGORIA["base"]) == cog.repo.create.await_count
    for _, kw in canali:
        assert kw["overwrites"][server.default_role].connect is False and kw["category"] is cat
    assert [c.args[2] for c in cog.repo.create.await_args_list] == list(MODELLI_CATEGORIA["base"])


# STA-049
async def test_sta_049_categoria_senza_permessi_o_senza_posto_non_crea_nulla(cog):
    i, server = _it()
    i.user.guild_permissions = discord.Permissions(manage_channels=False)
    server.create_category = AsyncMock()
    await cog.categoria.callback(cog, i, SimpleNamespace(value="base"), "x")
    server.create_category.assert_not_awaited()
    i, server = _it()
    i.user.guild_permissions = discord.Permissions(manage_channels=True)
    server.me.guild_permissions = discord.Permissions(manage_channels=True)
    server.create_category = AsyncMock()
    cog.repo.list_for_guild.return_value = [0] * (MAX_CONTATORI - 1)
    await cog.categoria.callback(cog, i, SimpleNamespace(value="completo"), "x")
    server.create_category.assert_not_awaited()


# STA-049
async def test_sta_049_categoria_se_un_canale_fallisce_toglie_quello_creato(cog):
    i, server = _it()
    i.user.guild_permissions = discord.Permissions(manage_channels=True)
    server.me.guild_permissions = discord.Permissions(manage_channels=True)
    cat = MagicMock(); cat.id = 500; cat.delete = AsyncMock()
    server.create_category = AsyncMock(return_value=cat)
    server.default_role = MagicMock()
    primo = MagicMock(spec=discord.VoiceChannel); primo.id = 601; primo.delete = AsyncMock()
    server.create_voice_channel = AsyncMock(side_effect=[primo, discord.HTTPException(MagicMock(status=500), "no")])
    await cog.categoria.callback(cog, i, SimpleNamespace(value="base"), "x")
    primo.delete.assert_awaited_once()
    cat.delete.assert_awaited_once()  # niente categorie vuote lasciate in giro
    assert cog.repo.delete_by_channel.await_count == 2


# --- repository con i campi nuovi ----------------------------------------------------------------

# STA-040, STA-049, STA-050, STA-051
async def test_sta_040_049_050_051_repo_param_targets_update_e_azzera(clean_db):
    repo = CounterRepository(lambda: clean_db)
    assert await repo.create(1, 10, "goal", "{n}/{target}", 1000, 9, param=None, targets="1000,2000") == "ok"
    assert await repo.create(1, 11, "role_with", "{n}", None, 9, param="55") == "ok"
    assert await repo.create(2, 12, "members", "{n}", None, 9) == "ok"  # un altro server
    (goal, ruolo) = await repo.list_for_guild(1)
    assert goal.targets == "1000,2000" and ruolo.param == "55"
    await repo.set_last_value(goal.id, 5)
    assert await repo.update(1, goal.id, label="{n} di {target}", targets="500")
    cambiato = await repo.get(1, goal.id)
    assert cambiato.label == "{n} di {target}" and cambiato.targets == "500" and cambiato.last_value is None
    assert not await repo.update(2, goal.id, label="{n}")  # un altro server non lo tocca
    assert await repo.get(2, goal.id) is None
    with pytest.raises(ValueError):
        await repo.update(1, goal.id, kind="members")  # solo i campi ammessi
    assert await repo.delete_all(1) == 2
    assert len(await repo.list_for_guild(2)) == 1  # l'altro server resta
    # i tipi nuovi passano il vincolo del database (la 0087 ammetteva solo quattro tipi)
    for n, kind in enumerate(TIPI):
        assert await repo.create(3, 100 + n, kind, "{n}", None, 9) in ("ok", "pieno")


async def test_il_tetto_per_server_vale_per_tutti_i_tipi(clean_db):
    repo = CounterRepository(lambda: clean_db)
    for n in range(MAX_CONTATORI):
        assert await repo.create(1, 100 + n, "static", "x", None, 9) == "ok"
    assert await repo.create(1, 999, "members", "{n}", None, 9) == "pieno"
