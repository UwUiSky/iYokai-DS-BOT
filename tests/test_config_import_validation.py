"""
tests/test_config_import_validation.py
=========================================
`/config import` deve validare lo schema PRIMA di scrivere e rifiutare i
dati sbagliati (PIANO_FIX R1, §4 Utility). BUG-31: anche i tipi dei
valori di `settings`, i nomi dei moduli e i file "strani" (NaN, BOM,
annidamento profondo…) devono dare un messaggio di validazione.
"""

import json
import re
from pathlib import Path

import pytest

from cogs.utility.config_history import (
    MAX_IMPORT_BYTES,
    SETTINGS_SCHEMA,
    ConfigHistoryCog,
    errore_schema_import,
)
from core.database import db
from core.premium import PremiumModule
from tests.support.discord_fakes import fake_guild, fake_interaction, fake_role
from tests.support.full_tree import build_full_bot, close_full_bot

GUILD = 777000602
RADICE = Path(__file__).parent.parent
VUOTA = {"modules": {}, "settings": {}, "language": "it"}
VALIDO = {"modules": {"tickets": True}, "settings": {"report_channel_id": 5}, "language": "it"}

# Un valore valido per ogni chiave conosciuta.
SETTINGS_VALIDE = {
    "log_channel_id": 111111111111111111,
    "mod_log_channel_id": 222222222222222222,
    "report_channel_id": 333333333333333333,
    "custom_command_requests_channel_id": 444444444444444444,
    "suggestions_channel_id": 555555555555555555,
    "ticket_category_id": 666666666666666666,
    "ticket_support_role_id": 777777777777777777,
    "ticket_support_role_ids": [888888888888888888, 999999999999999999],
    "spam_trap_staff_role_ids": [],
    "mute_role_id": 123123123123123123,
    "admin_role_id": 234234234234234234,
    "mod_role_id": 345345345345345345,
    "modban_role_id": 456456456456456456,
    "backup_restore_mode": "classic_invite",
    "backup_auto_invite_on_join": True,
    "logging_soundboard_watermark": "2026-10-01T12:00:00+00:00",
}


@pytest.fixture
def modulo_tickets(reset_premium_registry):
    """
    Il registry vero si riempie caricando i cog: qui basta il modulo
    usato da VALIDO, se un altro test non ha già caricato quello vero.
    """
    if reset_premium_registry.get("tickets") is None:
        reset_premium_registry.register(
            PremiumModule(name="tickets", display_name="Ticket", description="x", category="tickets")
        )


@pytest.mark.usefixtures("modulo_tickets")
class TestErroreSchemaImport:
    def test_dati_validi_nessun_errore(self):
        assert errore_schema_import(VALIDO) is None

    def test_tutte_le_chiavi_conosciute_con_valori_validi(self):
        assert set(SETTINGS_VALIDE) == set(SETTINGS_SCHEMA)
        assert errore_schema_import({**VALIDO, "settings": SETTINGS_VALIDE}) is None

    @pytest.mark.parametrize(
        "dati",
        [
            {**VALIDO, "modules": []},
            {**VALIDO, "modules": {"tickets": "si"}},
            {**VALIDO, "modules": {"": True}},
            {**VALIDO, "settings": [1]},
            {**VALIDO, "language": "xx"},
            {**VALIDO, "language": 3},
            {**VALIDO, "language": []},
            {"modules": {}, "settings": {}},
            [],
        ],
    )
    def test_dati_sbagliati_vengono_rifiutati(self, dati):
        assert errore_schema_import(dati) is not None

    @pytest.mark.parametrize(
        "settings",
        [
            {"ticket_support_role_ids": None},
            {"log_channel_id": []},
            {"log_channel_id": None},
            {"log_channel_id": "123"},
            {"log_channel_id": True},
            {"log_channel_id": 1.5},
            {"log_channel_id": 0},
            {"log_channel_id": -5},
            {"log_channel_id": 2**63},
            {"log_channel_id": 10**400},
            {"ticket_support_role_ids": 5},
            {"ticket_support_role_ids": [1, "2"]},
            {"ticket_support_role_ids": [1, None]},
            {"ticket_support_role_ids": [[1]]},
            {"ticket_support_role_ids": list(range(1, 1000))},
            {"backup_auto_invite_on_join": 1},
            {"backup_restore_mode": "inventata"},
            {"backup_restore_mode": 3},
            {"logging_soundboard_watermark": "ieri"},
            {"logging_soundboard_watermark": "2026-10-01\x00"},
            {"logging_soundboard_watermark": 5},
        ],
    )
    def test_valore_di_tipo_sbagliato_viene_rifiutato(self, settings):
        errore = errore_schema_import({**VALIDO, "settings": settings})
        assert errore is not None and next(iter(settings)) in errore

    def test_chiave_sconosciuta_in_settings_viene_rifiutata(self):
        errore = errore_schema_import({**VALIDO, "settings": {"chiave_inventata": 1}})
        assert errore is not None and "chiave_inventata" in errore

    def test_modulo_sconosciuto_viene_rifiutato(self):
        errore = errore_schema_import({**VALIDO, "modules": {"modulo_inventato": True}})
        assert errore is not None and "modulo_inventato" in errore

    def test_il_messaggio_resta_corto_e_inviabile_anche_con_nomi_ostili(self):
        nomi = {("x" * 500) + str(n): True for n in range(200)}
        nomi["\ud800`@everyone\x00"] = True
        errore = errore_schema_import({**VALIDO, "modules": nomi})
        assert len(errore) < 1500
        errore.encode("utf-8")  # nessun surrogato isolato nel messaggio
        assert "\x00" not in errore


def test_ogni_setting_usata_nel_codice_e_nello_schema():
    """Invariante: una nuova chiave SETTING_* va aggiunta a SETTINGS_SCHEMA."""
    chiavi = set()
    for cartella in ("cogs", "core"):
        for percorso in (RADICE / cartella).rglob("*.py"):
            chiavi |= set(
                re.findall(
                    r'^SETTING_\w+ = "(\w+)"', percorso.read_text(encoding="utf-8"), re.MULTILINE
                )
            )
    assert len(chiavi) >= 13
    assert chiavi <= set(SETTINGS_SCHEMA), chiavi - set(SETTINGS_SCHEMA)


class _FakeFile:
    def __init__(self, contenuto: bytes, size: int | None = None):
        self._contenuto = contenuto
        self.size = len(contenuto) if size is None else size

    async def read(self):
        return self._contenuto


@pytest.fixture(autouse=True)
def _pool(monkeypatch, clean_db):
    import core.database as database_module

    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    database_module.db._modules_cache.clear()
    return clean_db


async def _importa(contenuto: bytes, size=None):
    cog = ConfigHistoryCog(bot=None)
    server = fake_guild(guild_id=GUILD)
    # i ruoli del bot (admin/mod/modban) devono esistere nel server
    ruoli_esistenti = {SETTINGS_VALIDE[k] for k in ("admin_role_id", "mod_role_id", "modban_role_id")}
    server.get_role.side_effect = lambda rid: fake_role(role_id=rid) if rid in ruoli_esistenti else None
    interazione = fake_interaction(guild=server)
    await cog.import_config.callback(cog, interazione, _FakeFile(contenuto, size))
    return interazione.response.send_message.call_args.args[0]


@pytest.mark.usefixtures("modulo_tickets")
async def test_import_con_schema_sbagliato_non_scrive_nulla():
    messaggio = await _importa(json.dumps({**VALIDO, "modules": {"tickets": "si"}}).encode())

    assert "✅" not in messaggio
    assert await db.get_full_config(GUILD) == VUOTA


@pytest.mark.usefixtures("modulo_tickets")
async def test_import_con_null_e_lista_vuota_al_posto_degli_id_viene_rifiutato():
    """BUG-31: questo file passava e poi ticket e log andavano in crash."""
    payload = {**VALIDO, "settings": {"ticket_support_role_ids": None, "log_channel_id": []}}

    messaggio = await _importa(json.dumps(payload).encode())

    assert "✅" not in messaggio
    assert await db.get_full_config(GUILD) == VUOTA


@pytest.mark.usefixtures("modulo_tickets")
async def test_import_di_un_file_troppo_grande_viene_rifiutato():
    # Un file VALIDO, solo più grande del limite: senza il controllo
    # della dimensione verrebbe importato.
    contenuto = json.dumps(VALIDO).encode() + b" " * MAX_IMPORT_BYTES
    assert errore_schema_import(json.loads(contenuto)) is None

    messaggio = await _importa(contenuto)

    assert "✅" not in messaggio and "troppo grande" in messaggio
    assert await db.get_full_config(GUILD) == VUOTA


@pytest.mark.usefixtures("modulo_tickets")
async def test_import_valido_scrive():
    messaggio = await _importa(json.dumps(VALIDO).encode())

    assert "✅" in messaggio
    assert (await db.get_full_config(GUILD))["modules"] == {"tickets": True}


@pytest.mark.usefixtures("modulo_tickets")
async def test_import_con_bom_utf8_viene_accettato():
    """Il Blocco note di Windows salva i .json con il BOM in testa."""
    messaggio = await _importa(b"\xef\xbb\xbf" + json.dumps(VALIDO).encode())

    assert "✅" in messaggio
    assert (await db.get_full_config(GUILD))["settings"] == {"report_channel_id": 5}


def _con_settings(testo_settings: str) -> bytes:
    return ('{"modules": {}, "language": "it", "settings": ' + testo_settings + "}").encode()


FILE_STRANI = {
    "NaN": _con_settings('{"log_channel_id": NaN}'),
    "Infinity": _con_settings('{"log_channel_id": -Infinity}'),
    "1e400": _con_settings('{"log_channel_id": 1e400}'),
    "nul_nella_chiave": _con_settings('{"log\\u0000channel": 1}'),
    "nul_nel_valore": _con_settings('{"backup_restore_mode": "classic\\u0000invite"}'),
    "surrogato_nella_chiave": _con_settings('{"\\ud800": 1}'),
    "surrogato_nel_valore": _con_settings('{"logging_soundboard_watermark": "\\udc00"}'),
    "surrogato_nel_modulo": b'{"modules": {"\\ud800": true}, "settings": {}, "language": "it"}',
    "surrogato_nella_lingua": b'{"modules": {}, "settings": {}, "language": "\\ud800"}',
    "centomila_parentesi": b"[" * 100_000,
    "centomila_oggetti": b'{"a":' * 100_000,
    "intero_enorme": _con_settings('{"log_channel_id": 1' + "0" * 400 + "}"),
    "intero_oltre_il_limite_di_python": _con_settings('{"log_channel_id": 1' + "0" * 5000 + "}"),
    "non_utf8": b"\xff\xfe{}",
    "vuoto": b"",
    "solo_bom": b"\xef\xbb\xbf",
}


@pytest.mark.parametrize("contenuto", FILE_STRANI.values(), ids=FILE_STRANI.keys())
async def test_file_strani_danno_un_messaggio_di_validazione_non_un_errore(contenuto):
    messaggio = await _importa(contenuto)  # non deve sollevare

    assert "✅" not in messaggio
    assert 0 < len(messaggio) <= 2000
    messaggio.encode("utf-8")  # inviabile a Discord
    assert await db.get_full_config(GUILD) == VUOTA


async def test_get_guild_setting_tratta_un_null_salvato_come_assente(clean_db):
    """Un `null` lasciato dal vecchio rollback non deve arrivare ai cog."""
    await clean_db.execute(
        "INSERT INTO guild_config (guild_id, settings) VALUES ($1, $2::jsonb)",
        GUILD,
        json.dumps({"ticket_support_role_ids": None, "log_channel_id": None}),
    )

    assert await db.get_guild_setting(GUILD, "ticket_support_role_ids", default=[]) == []
    assert await db.get_guild_setting(GUILD, "log_channel_id") is None
    assert await db.get_guild_setting(GUILD, "log_channel_id", default=7) == 7


async def test_ticket_con_null_nei_ruoli_di_supporto_non_va_in_crash(clean_db):
    from cogs.tickets.tickets import _support_role_ids

    await clean_db.execute(
        "INSERT INTO guild_config (guild_id, settings) VALUES ($1, $2::jsonb)",
        GUILD,
        json.dumps({"ticket_support_role_ids": None, "ticket_support_role_id": 42}),
    )

    assert await _support_role_ids(GUILD) == [42]


async def test_migrazione_toglie_le_chiavi_null_da_settings(clean_db):
    from core.migrations import discover_migrations

    migrazione = next(m for m in discover_migrations() if "settings_senza_null" in m.name)
    for guild_id, settings in [
        (1, {"a": None, "log_channel_id": 5, "lista": [1, None]}),
        (2, {"solo_null": None}),
        (3, {"report_channel_id": 9}),
    ]:
        await clean_db.execute(
            "INSERT INTO guild_config (guild_id, settings) VALUES ($1, $2::jsonb)",
            guild_id,
            json.dumps(settings),
        )

    await clean_db.execute(migrazione.path.read_text(encoding="utf-8"))

    righe = await clean_db.fetch("SELECT guild_id, settings FROM guild_config ORDER BY guild_id")
    assert [json.loads(r["settings"]) for r in righe] == [
        {"log_channel_id": 5, "lista": [1, None]},
        {},
        {"report_channel_id": 9},
    ]


@pytest.mark.usefixtures("modulo_tickets")
async def test_rollback_di_un_import_non_riporta_in_vita_i_null(clean_db):
    """Lo storico vecchio può contenere `null`: ripristinandolo non devono tornare."""
    await clean_db.execute(
        "INSERT INTO guild_config (guild_id, settings) VALUES ($1, $2::jsonb)",
        GUILD,
        json.dumps({"ticket_support_role_ids": None, "report_channel_id": 5}),
    )
    assert "✅" in await _importa(json.dumps(VALIDO).encode())
    voce = (await db.get_config_history(GUILD, limit=1))[0]

    assert await db.rollback_config_change(voce.id, rolled_back_by=1) is True

    assert (await db.get_full_config(GUILD))["settings"] == {"report_channel_id": 5}


async def test_export_poi_import_con_il_registry_vero_riproduce_la_configurazione(clean_db):
    """Giro completo con tutti i moduli reali attivi e tutte le chiavi conosciute."""
    from core.premium import registry

    bot, falliti = await build_full_bot()
    try:
        assert not falliti
        nomi = [m.name for m in registry.all_modules()]
        assert len(nomi) >= 32
        for nome in nomi:
            await db.set_module_active_for_guild(GUILD, nome, True)
        for chiave, valore in SETTINGS_VALIDE.items():
            await db.set_guild_setting(GUILD, chiave, valore)
        await db.set_guild_language(GUILD, "en")
        originale = await db.get_full_config(GUILD)

        cog = bot.get_cog("ConfigHistoryCog")
        interazione = fake_interaction(guild=fake_guild(guild_id=GUILD))
        await cog.export.callback(cog, interazione)
        esportato = interazione.response.send_message.call_args.kwargs["file"].fp.read()

        await db.reset_guild_config(GUILD)
        messaggio = await _importa(esportato)

        assert "✅" in messaggio
        assert await db.get_full_config(GUILD) == originale
    finally:
        await close_full_bot(bot)


@pytest.mark.usefixtures("modulo_tickets")
async def test_export_non_scrive_le_voci_vuote_e_il_file_si_reimporta(clean_db):
    """#136: una impostazione a `null` non finisce nel file, che si reimporta."""
    await clean_db.execute(
        "INSERT INTO guild_config (guild_id, settings) VALUES ($1, $2::jsonb)",
        GUILD,
        json.dumps({"ticket_support_role_ids": None, "report_channel_id": 5, "mute_role_id": None}),
    )
    cog = ConfigHistoryCog(bot=None)
    interazione = fake_interaction(guild=fake_guild(guild_id=GUILD))

    await cog.export.callback(cog, interazione)
    esportato = interazione.response.send_message.call_args.kwargs["file"].fp.read()

    assert json.loads(esportato)["settings"] == {"report_channel_id": 5}
    assert "✅" in await _importa(esportato)
    assert (await db.get_full_config(GUILD))["settings"] == {"report_channel_id": 5}


@pytest.mark.usefixtures("modulo_tickets")
async def test_export_toglie_null_nelle_liste_e_chiavi_fuori_schema(clean_db):
    await clean_db.execute(
        "INSERT INTO guild_config (guild_id, settings) VALUES ($1, $2::jsonb)",
        GUILD,
        json.dumps({"ticket_support_role_ids": [5, None, 6], "chiave_vecchia": 3, "mute_role_id": 7}),
    )
    cog = ConfigHistoryCog(bot=None)
    interazione = fake_interaction(guild=fake_guild(guild_id=GUILD))

    await cog.export.callback(cog, interazione)
    esportato = interazione.response.send_message.call_args.kwargs["file"].fp.read()

    assert json.loads(esportato)["settings"] == {"ticket_support_role_ids": [5, 6], "mute_role_id": 7}
    assert "✅" in await _importa(esportato)
