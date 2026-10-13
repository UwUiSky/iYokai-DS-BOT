"""
tests/test_log_catalogo.py
==========================
Voci piccole del catalogo log (#119): ignorare chi ha certi ruoli (LOG-022) e i messaggi che
corrispondono a un'espressione regolare (LOG-024), log di timeout (LOG-009), cambio di
nome utente, nome visualizzato e avatar (LOG-007, LOG-008), palchi (LOG-013).
LOG-021 (categorie e thread) e LOG-023 (bot) erano già fatti: qui solo la prova che restano così.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import cogs.logging.advanced_logs as advanced
import cogs.logging.basic_logs as basic
import cogs.logging.log_config as config
import cogs.logging.message_logs as messaggi
from core import message_log_logic as logica
from core.message_log_logic import Ignorati
from core.repositories.log_ignora_repo import LogIgnoraRepository
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_member, fake_role, fake_text_channel

SERVER = 600


# ====================================================================
# LOG-022 / LOG-024 — regole pure
# ====================================================================
def _ign(**kw):
    return Ignorati(**kw)


def test_chi_ha_un_ruolo_ignorato_non_finisce_nel_log():
    ig = _ign(ruoli=frozenset({7}))
    assert logica.da_ignorare(ig, channel_id=1, author_id=2, testo="ciao", ruoli_autore=[3, 7])
    assert not logica.da_ignorare(ig, channel_id=1, author_id=2, testo="ciao", ruoli_autore=[3])
    assert not logica.da_ignorare(ig, channel_id=1, author_id=2, testo="ciao")


def test_il_testo_che_corrisponde_all_espressione_non_finisce_nel_log():
    ig = _ign(regex=(r"^!\w+", "https?://\\S+\\.xyz"))
    assert logica.da_ignorare(ig, channel_id=1, author_id=2, testo="!ban qualcuno")
    assert logica.da_ignorare(ig, channel_id=1, author_id=2, testo="guarda HTTPS://sito.xyz subito")
    assert not logica.da_ignorare(ig, channel_id=1, author_id=2, testo="ciao a tutti")
    assert not logica.da_ignorare(ig, channel_id=1, author_id=2, testo=None)


def test_l_espressione_guarda_solo_i_primi_500_caratteri():
    ig = _ign(regex=("segreto",))
    assert not logica.da_ignorare(ig, channel_id=1, author_id=2, testo="a" * 600 + "segreto")


@pytest.mark.parametrize(
    "schema",
    ["(a+)+$", "(a|aa)+", "a*a*a*b", r"(\w)\1", "x" * 101, "([", "", "(?=x)", "(x){3}", r"\\*\\*\\*\\*x"],
)
def test_espressioni_pericolose_o_rotte_rifiutate(schema):
    assert logica.regex_non_valida(schema) is not None


@pytest.mark.parametrize("schema", ["spam|truffa", r"^!ban\b", r"https?://\S+", "a.*b.*c", "(ab)?c", "[a*+]+x"])
def test_espressioni_semplici_accettate(schema):
    assert logica.regex_non_valida(schema) is None


def test_scelta_di_ruolo_ed_espressione():
    assert logica.scegli_bersaglio(None, None, None, role_id=5) == ("ruolo", "5")
    assert logica.scegli_bersaglio(None, None, None, regex="spam|truffa") == ("regex", "spam|truffa")
    assert "troppo costosa" in logica.scegli_bersaglio(None, None, None, regex="a*a*a*b")
    assert "una sola" in logica.scegli_bersaglio(None, None, None, role_id=5, regex="x")


def test_l_elenco_mostra_ruoli_ed_espressioni():
    testo = logica.testo_elenco_ignorati(_ign(ruoli=frozenset({7}), regex=("spam",)))
    assert "<@&7>" in testo and "`spam`" in testo


def test_categorie_thread_e_bot_restano_ignorati():
    ig = _ign(canali=frozenset({10}))
    assert logica.da_ignorare(ig, channel_id=5, author_id=1, testo="x", category_id=10)  # LOG-021
    assert logica.da_ignorare(ig, channel_id=5, author_id=1, testo="x", thread_parent_id=10)  # LOG-021
    bot = SimpleNamespace(author=SimpleNamespace(bot=True, id=1, roles=[]), content="x")
    assert messaggi._scartato(_ign(), None, bot, 5)  # LOG-023


def test_il_messaggio_di_chi_ha_un_ruolo_ignorato_e_scartato():
    autore = fake_member(2, roles=[fake_role(role_id=7)])
    autore.bot = False
    messaggio = SimpleNamespace(author=autore, content="ciao")
    assert messaggi._scartato(_ign(ruoli=frozenset({7})), None, messaggio, 5)
    assert not messaggi._scartato(_ign(ruoli=frozenset({8})), None, messaggio, 5)


# ====================================================================
# LOG-022 / LOG-024 — database e comando
# ====================================================================
@pytest.fixture
def repo(clean_db, monkeypatch):
    r = LogIgnoraRepository(pool_provider=lambda: clean_db)
    monkeypatch.setattr(config, "log_ignora_repo", r)
    return r


async def test_ruoli_ed_espressioni_si_salvano_e_si_rileggono(repo):
    assert await repo.aggiungi(SERVER, "ruolo", "7", 200)
    assert await repo.aggiungi(SERVER, "regex", "spam", 200)
    ig = await repo.carica(SERVER)
    assert ig.ruoli == frozenset({7}) and ig.regex == ("spam",)


async def test_al_massimo_cinque_espressioni_per_server(repo):
    for n in range(5):
        assert await repo.aggiungi(SERVER, "regex", f"voce{n}", 200)
    assert not await repo.aggiungi(SERVER, "regex", "voce5", 200)
    assert await repo.aggiungi(SERVER, "ruolo", "9", 200)  # il tetto vale solo per le espressioni


async def test_comando_ignora_con_ruolo_ed_espressione(repo):
    cog = config.LogConfigCog(bot=None)
    ix = fake_interaction(guild=fake_guild(guild_id=SERVER))
    ruolo = fake_role(role_id=7)
    await cog.ignora.callback(cog, ix, "aggiungi", None, None, None, ruolo, None)
    await cog.ignora.callback(cog, ix, "aggiungi", None, None, None, None, "spam|truffa")
    ig = await repo.carica(SERVER)
    assert ig.ruoli == frozenset({7}) and ig.regex == ("spam|truffa",)

    ix2 = fake_interaction(guild=fake_guild(guild_id=SERVER))
    await cog.ignora.callback(cog, ix2, "aggiungi", None, None, None, None, "(a+)+$")
    assert "rallenterebbe" in ix2.response.send_message.call_args.args[0]
    assert (await repo.carica(SERVER)).regex == ("spam|truffa",)

    await cog.ignora.callback(cog, ix, "rimuovi", None, None, None, ruolo, None)
    assert (await repo.carica(SERVER)).ruoli == frozenset()


# ====================================================================
# LOG-009 — timeout
# ====================================================================
ADESSO = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
FRA_UN_ORA = ADESSO + timedelta(hours=1)


def test_timeout_dato_tolto_cambiato_o_scaduto():
    assert basic.timeout_cambio(None, FRA_UN_ORA, ADESSO) == ("dato", FRA_UN_ORA)
    assert basic.timeout_cambio(FRA_UN_ORA, None, ADESSO) == ("tolto", None)
    assert basic.timeout_cambio(FRA_UN_ORA, FRA_UN_ORA + timedelta(hours=1), ADESSO)[0] == "cambiato"
    assert basic.timeout_cambio(FRA_UN_ORA, FRA_UN_ORA, ADESSO) is None
    assert basic.timeout_cambio(ADESSO - timedelta(hours=1), None, ADESSO) is None  # scaduto da solo
    assert basic.timeout_cambio(None, None, ADESSO) is None


@pytest.fixture
def log_di_base(monkeypatch):
    monkeypatch.setattr(basic.db, "is_module_active_for_guild", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(basic.event_log_repo, "log_event", AsyncMock())
    canale = fake_text_channel(900, "log")
    monkeypatch.setattr(basic, "_get_log_channel", AsyncMock(return_value=canale))
    invio = AsyncMock()
    monkeypatch.setattr(basic, "_send_log", invio)
    return invio


def _membro(timeout, server):
    m = fake_member(5, "mario")
    m.guild = server
    m.roles, m.nick, m.timed_out_until = [], None, timeout
    return m


async def test_timeout_dato_dal_menu_di_discord_finisce_nel_log(log_di_base, monkeypatch):
    monkeypatch.setattr(discord.utils, "utcnow", lambda: ADESSO)
    server = fake_guild(guild_id=SERVER)
    cog = basic.BasicLogsCog(bot=None)
    await cog.on_member_update(_membro(None, server), _membro(FRA_UN_ORA, server))
    embed = log_di_base.await_args.args[1]
    assert embed.title == "⏳ Timeout dato"
    assert basic.event_log_repo.log_event.await_args.args[1] == "timeout_update"
    log_di_base.reset_mock()
    await cog.on_member_update(_membro(FRA_UN_ORA, server), _membro(None, server))
    assert log_di_base.await_args.args[1].title == "✅ Timeout tolto"


async def test_nessun_log_se_cambia_altro_e_il_timeout_no(log_di_base, monkeypatch):
    monkeypatch.setattr(discord.utils, "utcnow", lambda: ADESSO)
    server = fake_guild(guild_id=SERVER)
    cog = basic.BasicLogsCog(bot=None)
    await cog.on_member_update(_membro(FRA_UN_ORA, server), _membro(FRA_UN_ORA, server))
    log_di_base.assert_not_awaited()


# ====================================================================
# LOG-007 / LOG-008 — profilo dell'utente
# ====================================================================
def _utente(name="mario", global_name="Mario", avatar_key="aaa"):
    u = SimpleNamespace(
        id=5, name=name, global_name=global_name,
        avatar=SimpleNamespace(key=avatar_key) if avatar_key else None,
        display_avatar=SimpleNamespace(url="https://cdn.example/a.png"),
    )
    return u


def test_cambi_del_profilo():
    assert basic.cambi_utente(_utente(), _utente()) == []
    assert basic.cambi_utente(_utente(), _utente(name="luigi")) == [("username", "mario", "luigi")]
    assert basic.cambi_utente(_utente(), _utente(global_name=None)) == [("display_name", "Mario", None)]
    assert basic.cambi_utente(_utente(), _utente(avatar_key="bbb")) == [("avatar", None, None)]
    assert basic.cambi_utente(_utente(avatar_key=None), _utente(avatar_key="x"))[0][0] == "avatar"


async def test_il_cambio_di_avatar_e_nome_va_nel_log_di_ogni_server_con_il_modulo(log_di_base, monkeypatch):
    attivo, spento = fake_guild(guild_id=1), fake_guild(guild_id=2)

    async def modulo_attivo(guild_id, nome):
        return guild_id == 1

    monkeypatch.setattr(basic.db, "is_module_active_for_guild", modulo_attivo, raising=False)
    nuovo = _utente(name="luigi", avatar_key="bbb")
    nuovo.mutual_guilds = [attivo, spento]
    cog = basic.BasicLogsCog(bot=None)
    await cog.on_user_update(_utente(), nuovo)
    titoli = [c.args[1].title for c in log_di_base.await_args_list]
    assert titoli == ["🧾 Nome utente cambiato", "🖼️ Avatar cambiato"]
    assert {c.args[0] for c in basic.event_log_repo.log_event.await_args_list} == {1}


async def test_utente_senza_cambi_o_senza_server_in_comune_non_scrive_nulla(log_di_base):
    cog = basic.BasicLogsCog(bot=None)
    await cog.on_user_update(_utente(), _utente())
    nuovo = _utente(name="x")
    nuovo.mutual_guilds = []
    await cog.on_user_update(_utente(), nuovo)
    log_di_base.assert_not_awaited()


# ====================================================================
# LOG-013 — palchi
# ====================================================================
@pytest.fixture
def avanzati(monkeypatch):
    monkeypatch.setattr(advanced, "logging_avanzato_attivo", AsyncMock(return_value=True))
    monkeypatch.setattr(advanced.event_log_repo, "log_event", AsyncMock())
    invio = AsyncMock()
    monkeypatch.setattr(advanced, "send_event_embed", invio)
    return advanced.AdvancedLogsCog(bot=MagicMock()), invio


def _palco(topic="Quiz", privacy=1):
    return SimpleNamespace(guild=fake_guild(guild_id=SERVER), topic=topic, channel_id=33, privacy_level=privacy)


async def test_palco_aperto_modificato_chiuso(avanzati):
    cog, invio = avanzati
    await cog.on_stage_instance_create(_palco())
    await cog.on_stage_instance_update(_palco("Quiz"), _palco("Quiz 2"))
    await cog.on_stage_instance_delete(_palco("Quiz 2"))
    assert [c.args[1] for c in invio.await_args_list] == ["voice_stage_create", "voice_stage_update", "voice_stage_delete"]
    assert "`Quiz` → `Quiz 2`" in invio.await_args_list[1].args[2]


async def test_palco_non_cambiato_o_log_avanzato_spento_non_scrive(avanzati, monkeypatch):
    cog, invio = avanzati
    await cog.on_stage_instance_update(_palco("Quiz"), _palco("Quiz"))
    invio.assert_not_awaited()
    monkeypatch.setattr(advanced, "logging_avanzato_attivo", AsyncMock(return_value=False))
    await cog.on_stage_instance_create(_palco())
    invio.assert_not_awaited()


def test_gli_eventi_dei_palchi_vanno_nel_tipo_voce():
    assert advanced.EVENT_TITLES["voice_stage_create"]
    assert "voice_stage_delete".startswith("voice_")  # send_event_embed li manda nel tipo «voce»
