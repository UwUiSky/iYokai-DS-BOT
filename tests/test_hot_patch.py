"""
tests/test_hot_patch.py
=======================
#141 (D21): aggiornamento a caldo del bot da GitHub o da file, riservato al proprietario.
"""

import dataclasses
import io
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest
from discord.ext import commands

from core import hot_patch as hp
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member

pytestmark = pytest.mark.asyncio

SHA = "a" * 40
BASE = "b" * 40


def _zip(files: dict[str, bytes]) -> bytes:
    uscita = io.BytesIO()
    with zipfile.ZipFile(uscita, "w") as z:
        for nome, dati in files.items():
            z.writestr(nome, dati)
    return uscita.getvalue()


# ----------------------------------------------------------------------
# Percorsi e pacchetti
# ----------------------------------------------------------------------
@pytest.mark.parametrize("buono", ["cogs/utility/ping.py", "core/i18n.py", "cogs/a/_privato.py"])
def test_percorsi_ammessi(buono):
    assert hp.valida_percorso(buono) == buono


@pytest.mark.parametrize(
    "cattivo",
    [
        "main.py", "tests/test_x.py", "cogs/utility/ping.txt", "../cogs/x.py", "cogs/../main.py", "/etc/passwd",
        "cogs//x.py", "cogs/x/.py", "core/hot_patch.py", "cogs/utility/ping.py\\..\\..\\x.py", "cogs", "",
        "cogs/uti lity/x.py", "cogs/9x.py", "scripts/x.py", "locales/it.json",
    ],
)
def test_percorsi_rifiutati(cattivo):
    with pytest.raises(hp.PatchRifiutata):
        hp.valida_percorso(cattivo)


def test_modulo_e_percorso_si_convertono():
    assert hp.modulo_a_percorso("cogs.utility.ping") == "cogs/utility/ping.py"
    assert hp.percorso_a_modulo("cogs/utility/ping.py") == "cogs.utility.ping"
    for cattivo in ("main", "os.path", "cogs..x"):
        with pytest.raises(hp.PatchRifiutata):
            hp.modulo_a_percorso(cattivo)


def test_zip_valido_e_zip_pericolosi():
    ok = hp.pacchetto_da_zip(_zip({"cogs/utility/x.py": b"x = 1\n", "core/y.py": b"y = 2\n"}))
    assert set(ok) == {"cogs/utility/x.py", "core/y.py"}
    for nomi in ({"../fuori.py": b"x"}, {"main.py": b"x"}, {"cogs/x.txt": b"x"}, {"/cogs/x.py": b"x"}):
        with pytest.raises(hp.PatchRifiutata):
            hp.pacchetto_da_zip(_zip(nomi))
    with pytest.raises(hp.PatchRifiutata):
        hp.pacchetto_da_zip(b"non e uno zip")
    with pytest.raises(hp.PatchRifiutata):
        hp.pacchetto_da_zip(_zip({}))
    troppi = {f"cogs/a/f{i}.py": b"x = 1\n" for i in range(hp.MAX_FILE + 1)}
    with pytest.raises(hp.PatchRifiutata):
        hp.pacchetto_da_zip(_zip(troppi))
    with pytest.raises(hp.PatchRifiutata):
        hp.pacchetto_da_zip(_zip({"cogs/a/grosso.py": b"#" * (hp.MAX_BYTE_FILE + 1)}))


def test_il_codice_deve_compilare():
    hp.controlla_pacchetto({"cogs/a/x.py": b"def f():\n    return 1\n"})
    with pytest.raises(hp.PatchRifiutata) as e:
        hp.controlla_pacchetto({"cogs/a/x.py": b"def f(:\n"})
    assert "non compila" in str(e.value) and "riga 1" in str(e.value)
    with pytest.raises(hp.PatchRifiutata):
        hp.controlla_pacchetto({})
    with pytest.raises(hp.PatchRifiutata):
        hp.controlla_pacchetto({"cogs/a/x.py": b"\x00 = 1"})  # byte nullo


# ----------------------------------------------------------------------
# Applicazione
# ----------------------------------------------------------------------
class _Registro:
    def __init__(self):
        self.voci = []

    async def registra(self, *args):
        self.voci.append(args)


class _BotFinto:
    def __init__(self, caricati=(), rotti=()):
        self.extensions = {m: object() for m in caricati}
        self.rotti = set(rotti)
        self.chiamate = []

    async def reload_extension(self, m):
        self.chiamate.append(("reload", m))
        if m in self.rotti:
            self.rotti.discard(m) if self.chiamate.count(("reload", m)) > 1 else None
            if ("reload", m) in self.chiamate[:-1]:
                return  # secondo ricaricamento (con il codice di prima): riesce
            raise RuntimeError("setup fallito con password=hunter2")

    async def load_extension(self, m):
        self.chiamate.append(("load", m))
        if m in self.rotti:
            raise RuntimeError("non si carica")
        self.extensions[m] = object()

    async def unload_extension(self, m):
        self.chiamate.append(("unload", m))
        self.extensions.pop(m, None)


@pytest.fixture
def radice(tmp_path):
    (tmp_path / "cogs" / "utility").mkdir(parents=True)
    (tmp_path / "core").mkdir()
    (tmp_path / "cogs" / "utility" / "a.py").write_text("VALORE = 'vecchio'\n")
    (tmp_path / "core" / "c.py").write_text("C = 'vecchio'\n")
    return tmp_path


async def _applica(bot, pacchetto, radice, registro, **kw):
    return await hp.applica_patch(
        bot, pacchetto, sorgente=kw.pop("sorgente", "allegato"), applicato_da=123, commit=kw.pop("commit", None),
        radice=radice, cartella_copie=radice / "data" / "copie", registro=registro,
    )


async def test_aggiorna_e_ricarica_il_cog_con_copia_del_vecchio(radice):
    bot, registro = _BotFinto(caricati=["cogs.utility.a"]), _Registro()
    esito = await _applica(bot, {"cogs/utility/a.py": b"VALORE = 'nuovo'\n"}, radice, registro, commit=SHA)
    assert esito.esito == "ok" and esito.ricaricati == ["cogs.utility.a"] and not esito.riavvio_necessario
    assert (radice / "cogs/utility/a.py").read_text() == "VALORE = 'nuovo'\n"
    assert (radice / "data/copie/cogs/utility/a.py").read_text() == "VALORE = 'vecchio'\n"
    assert not list(radice.rglob("*.nuovo"))
    assert registro.voci == [(123, "allegato", SHA, ["cogs/utility/a.py"], "ok", False, None)]


async def test_un_file_di_core_chiede_il_riavvio_e_non_ricarica_niente(radice):
    bot, registro = _BotFinto(), _Registro()
    esito = await _applica(bot, {"core/c.py": b"C = 'nuovo'\n"}, radice, registro)
    assert esito.esito == "ok" and esito.riavvio_necessario and esito.ricaricati == [] and bot.chiamate == []
    assert registro.voci[0][5] is True


async def test_cog_nuovo_viene_caricato(radice):
    bot, registro = _BotFinto(), _Registro()
    esito = await _applica(bot, {"cogs/utility/nuovo.py": b"X = 1\n"}, radice, registro)
    assert esito.ricaricati == ["cogs.utility.nuovo"] and ("load", "cogs.utility.nuovo") in bot.chiamate


async def test_se_il_cog_non_si_ricarica_si_rimette_tutto_com_era(radice):
    bot, registro = _BotFinto(caricati=["cogs.utility.a", "cogs.utility.b"], rotti=["cogs.utility.b"]), _Registro()
    (radice / "cogs/utility/b.py").write_text("B = 'vecchio'\n")
    pacchetto = {
        "cogs/utility/a.py": b"VALORE = 'nuovo'\n",
        "cogs/utility/b.py": b"B = 'nuovo'\n",
        "cogs/utility/c_nuovo.py": b"N = 1\n",
        "core/c.py": b"C = 'nuovo'\n",
    }
    esito = await _applica(bot, pacchetto, radice, registro)
    assert esito.esito == "ripristinato" and "cogs.utility.b" in esito.errori
    assert (radice / "cogs/utility/a.py").read_text() == "VALORE = 'vecchio'\n"
    assert (radice / "cogs/utility/b.py").read_text() == "B = 'vecchio'\n"
    assert (radice / "core/c.py").read_text() == "C = 'vecchio'\n"
    assert not (radice / "cogs/utility/c_nuovo.py").exists()  # non esisteva prima: sparisce
    assert ("reload", "cogs.utility.a") in bot.chiamate[1:]  # `a` riparte con il codice di prima
    assert registro.voci[0][4] == "ripristinato"


async def test_codice_che_non_compila_non_tocca_niente(radice):
    bot, registro = _BotFinto(caricati=["cogs.utility.a"]), _Registro()
    esito = await _applica(
        bot, {"cogs/utility/a.py": b"VALORE = 'nuovo'\n", "cogs/utility/b.py": b"def f(:\n"}, radice, registro
    )
    assert esito.esito == "rifiutato" and "non compila" in esito.nota
    assert (radice / "cogs/utility/a.py").read_text() == "VALORE = 'vecchio'\n"
    assert bot.chiamate == [] and registro.voci[0][4] == "rifiutato"


async def test_il_registro_vero_conserva_chi_quando_e_cosa(clean_db, monkeypatch, radice):
    import core.database as database_module
    from core.repositories.hot_patch_log_repo import hot_patch_log_repo

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    await hp.applica_patch(
        _BotFinto(), {"core/c.py": b"C = 2\n"}, sorgente="github", applicato_da=123, commit=SHA,
        radice=radice, cartella_copie=radice / "copie",
    )
    voce = (await hot_patch_log_repo.ultimi())[0]
    assert (voce.applied_by, voce.source, voce.commit_sha, voce.files, voce.outcome, voce.restart_needed) == (
        123, "github", SHA, ["core/c.py"], "ok", True,
    )


# ----------------------------------------------------------------------
# GitHub
# ----------------------------------------------------------------------
class _Risposta:
    def __init__(self, stato, corpo):
        self.status, self._corpo = stato, corpo
        self.content_length = len(corpo) if isinstance(corpo, bytes) else None
        self.content = self

    async def read(self, n):
        return self._corpo[:n]

    async def json(self):
        return self._corpo

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _Sessione:
    def __init__(self, risposte):
        self.risposte, self.richieste = risposte, []

    def get(self, url, headers=None, params=None, timeout=None):
        self.richieste.append((url, headers, params))
        for parte, risposta in self.risposte.items():
            if url.endswith(parte):
                return _Risposta(*risposta)
        return _Risposta(404, {})


def _github(extra=None, token=""):
    risposte = {
        "/commits/main": (200, {"sha": SHA}),
        f"/compare/{SHA}...main": (200, {"status": "identical"}),
        f"/compare/{BASE}...{SHA}": (200, {"files": [
            {"filename": "cogs/utility/a.py", "status": "modified"},
            {"filename": "core/c.py", "status": "added"},
            {"filename": "locales/it.json", "status": "modified"},
            {"filename": "main.py", "status": "modified"},
            {"filename": "cogs/utility/vecchio.py", "status": "removed"},
        ]}),
        "/contents/cogs/utility/a.py": (200, b"VALORE = 'github'\n"),
        "/contents/core/c.py": (200, b"C = 'github'\n"),
    }
    risposte.update(extra or {})
    sessione = _Sessione(risposte)
    return hp.ClienteGitHub(sessione, "UwUiSky/iYokai-DS-BOT", token), sessione


async def test_da_github_prende_solo_i_py_ammessi_dal_commit_scelto():
    cliente, sessione = _github(token="segreto-github")
    pacchetto, sha, ignorati = await hp.pacchetto_da_github(cliente, "main", BASE)
    assert sha == SHA and ignorati == 2  # json e main.py; il file tolto non si scarica né si cancella
    assert pacchetto == {"cogs/utility/a.py": b"VALORE = 'github'\n", "core/c.py": b"C = 'github'\n"}
    assert all(r[0].startswith("https://api.github.com/repos/UwUiSky/iYokai-DS-BOT/") for r in sessione.richieste)
    assert all(r[1]["Authorization"] == "Bearer segreto-github" for r in sessione.richieste)
    assert ("ref", SHA) in [(k, v) for r in sessione.richieste if r[2] for k, v in r[2].items()]


async def test_da_github_un_commit_fuori_da_main_si_rifiuta():
    cliente, _ = _github({f"/compare/{SHA}...main": (200, {"status": "diverged"}), f"/commits/{SHA}": (200, {"sha": SHA})})
    with pytest.raises(hp.PatchRifiutata, match="main"):
        await hp.pacchetto_da_github(cliente, SHA, BASE)


async def test_da_github_riferimenti_e_errori():
    cliente, _ = _github()
    for cattivo in ("develop", "../x", "abc", "main; rm -rf /"):
        with pytest.raises(hp.PatchRifiutata):
            await hp.pacchetto_da_github(cliente, cattivo, BASE)
    with pytest.raises(hp.PatchRifiutata, match="quale commit"):
        await hp.pacchetto_da_github(cliente, "main", None)
    cliente, _ = _github({"/commits/main": (403, {})})
    with pytest.raises(hp.PatchRifiutata, match="rifiutato l'accesso"):
        await hp.pacchetto_da_github(cliente, "main", BASE)
    cliente, _ = _github({"/commits/main": (200, {"sha": "zzz"})})
    with pytest.raises(hp.PatchRifiutata):
        await hp.pacchetto_da_github(cliente, "main", BASE)
    with pytest.raises(hp.PatchRifiutata):
        hp.ClienteGitHub(object(), "non un repo")


async def test_da_github_un_solo_modulo_senza_confronto():
    cliente, sessione = _github()
    pacchetto, sha, ignorati = await hp.pacchetto_da_github(cliente, "main", None, solo="cogs/utility/a.py")
    assert pacchetto == {"cogs/utility/a.py": b"VALORE = 'github'\n"} and ignorati == 0
    with pytest.raises(hp.PatchRifiutata):
        await hp.pacchetto_da_github(cliente, "main", None, solo="main.py")


async def test_da_github_file_troppo_grande_o_troppi_file():
    grosso = b"#" * (hp.MAX_BYTE_FILE + 5)
    cliente, _ = _github({"/contents/cogs/utility/a.py": (200, grosso)})
    with pytest.raises(hp.PatchRifiutata, match="troppo grande"):
        await hp.pacchetto_da_github(cliente, "main", BASE)
    molti = [{"filename": f"cogs/a/f{i}.py", "status": "added"} for i in range(hp.MAX_FILE + 1)]
    cliente, _ = _github({f"/compare/{BASE}...{SHA}": (200, {"files": molti})})
    with pytest.raises(hp.PatchRifiutata, match="Troppi file"):
        await hp.pacchetto_da_github(cliente, "main", BASE)


# ----------------------------------------------------------------------
# Il comando dell'owner
# ----------------------------------------------------------------------
@pytest.fixture
def cog(monkeypatch):
    import cogs.utility.owner_premium as modulo

    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    cog = modulo.OwnerPremiumCog(bot)
    monkeypatch.setattr(modulo, "config", SimpleNamespace(OWNER_ID=123, ENABLE_HOT_PATCH=True, HOT_PATCH_REPO="a/b", HOT_PATCH_GITHUB_TOKEN="", PREMIUM_ALPHA_UNLOCK_ALL=True))
    return cog, modulo


def _i(user_id=123):
    return fake_interaction(guild=fake_guild(1), user=fake_member(user_id))


def _allegato(nome, dati):
    a = AsyncMock(spec=discord.Attachment)
    a.filename, a.size = nome, len(dati)
    a.read = AsyncMock(return_value=dati)
    return a


async def test_spento_senza_enable_hot_patch_e_solo_per_l_owner(cog):
    c, modulo = cog
    modulo.config = dataclasses.replace(modulo.config, ENABLE_HOT_PATCH=False) if dataclasses.is_dataclass(modulo.config) else SimpleNamespace(**{**vars(modulo.config), "ENABLE_HOT_PATCH": False})
    i = _i()
    await c.owner_cog_reload.callback(c, i, "cogs.utility.ping", None, _allegato("ping.py", b"x = 1\n"), False)
    assert "ENABLE_HOT_PATCH=1" in i.response.send_message.call_args.args[0]
    modulo.config = SimpleNamespace(**{**vars(modulo.config), "ENABLE_HOT_PATCH": True})
    i = _i(user_id=999)
    await c.owner_cog_reload.callback(c, i, None, "main", None, False)
    assert "Solo il proprietario" in i.response.send_message.call_args.args[0]


async def test_il_vecchio_reload_funziona_ancora(cog):
    c, modulo = cog
    c.bot.reload_extension = AsyncMock()
    i = _i()
    await c.owner_cog_reload.callback(c, i, "cogs.utility.ping", None, None, False)
    c.bot.reload_extension.assert_awaited_once_with("cogs.utility.ping")
    assert "Ricaricato" in i.response.send_message.call_args.args[0]
    i = _i()
    await c.owner_cog_reload.callback(c, i, None, None, None, False)
    assert "Indica il modulo" in i.response.send_message.call_args.args[0]


async def test_allegato_py_senza_modulo_e_due_sorgenti_si_rifiutano(cog, clean_db, monkeypatch):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    c, modulo = cog
    i = _i()
    await c.owner_cog_reload.callback(c, i, None, "main", _allegato("x.py", b"x"), False)
    assert "una sola sorgente" in i.response.send_message.call_args.args[0]
    i = _i()
    await c.owner_cog_reload.callback(c, i, None, None, _allegato("x.py", b"x = 1\n"), False)
    assert "indica anche il modulo" in i.followup.send.call_args.args[0]
    i = _i()
    await c.owner_cog_reload.callback(c, i, None, None, _allegato("x.exe", b"MZ"), False)
    assert "rifiutato" in i.followup.send.call_args.args[0]


async def test_allegato_e_registro_dal_comando(cog, clean_db, monkeypatch, tmp_path):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    c, modulo = cog
    visto = {}

    async def finto(bot, pacchetto, **kw):
        visto.update(pacchetto=pacchetto, **kw)
        return hp.EsitoPatch("ok", sorted(pacchetto), ["cogs.utility.ping"], False)

    monkeypatch.setattr(hp, "applica_patch", finto)
    i = _i()
    await c.owner_cog_reload.callback(c, i, "cogs.utility.ping", None, _allegato("ping.py", b"x = 1\n"), False)
    assert visto["pacchetto"] == {"cogs/utility/ping.py": b"x = 1\n"} and visto["applicato_da"] == 123
    assert "Aggiornati 1 file" in i.followup.send.call_args.args[0]

    i = _i()
    await c.owner_cog_reload.callback(c, i, None, None, _allegato("p.zip", _zip({"core/y.py": b"y = 1\n"})), False)
    assert "Serve il riavvio" not in i.followup.send.call_args.args[0]  # l'esito finto non lo chiede

    monkeypatch.setattr(hp, "applica_patch", AsyncMock(return_value=hp.EsitoPatch("ok", ["core/y.py"], [], True)))
    i = _i()
    await c.owner_cog_reload.callback(c, i, None, None, _allegato("p.zip", _zip({"core/y.py": b"y = 1\n"})), False)
    assert "Serve il riavvio" in i.followup.send.call_args.args[0]

    # un rifiuto prima dell'applicazione finisce comunque nel registro
    i = _i()
    await c.owner_cog_reload.callback(c, i, None, None, _allegato("p.zip", _zip({"main.py": b"x"})), False)
    from core.repositories.hot_patch_log_repo import hot_patch_log_repo

    assert (await hot_patch_log_repo.ultimi(1))[0].outcome == "rifiutato"

    i = _i()
    await c.owner_cog_reload.callback(c, i, None, None, None, True)
    assert i.response.send_message.called or i.followup.send.called or i.response.defer.called


def test_testo_dell_esito():
    from cogs.utility.owner_premium import testo_esito_aggiornamento

    assert "rifiutato" in testo_esito_aggiornamento(hp.EsitoPatch("rifiutato", nota="no"), None)
    t = testo_esito_aggiornamento(hp.EsitoPatch("ripristinato", ["cogs/a.py"], errori={"cogs.a": "RuntimeError: x"}, nota="Tornato."), SHA)
    assert "Tornato." in t and "cogs.a" in t
    t = testo_esito_aggiornamento(hp.EsitoPatch("ok", ["core/c.py"], [], True), SHA)
    assert SHA[:7] in t and "riavvio" in t
