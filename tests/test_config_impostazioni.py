"""
tests/test_config_impostazioni.py
=================================
SPEC §24.2 (#91): impostazioni interne dei moduli, un punto unico per la pagina del pannello. Stessi controlli
dello schema, storico, niente chiavi riservate al proprietario.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import core.database as database_module
from core import config_impostazioni as ci
from core.config_schema import ImpostazioneNonValida
from core.database import db

G = 4400


def _ruolo(i, nome, default=False, managed=False):
    return SimpleNamespace(id=i, name=nome, is_default=lambda: default, managed=managed)


def _guild():
    ruoli = [_ruolo(G, "@everyone", default=True), _ruolo(11, "Mod"), _ruolo(12, "Bot", managed=True)]
    testo = [SimpleNamespace(id=21, name="log"), SimpleNamespace(id=22, name="generale")]
    voce = [SimpleNamespace(id=31, name="Musica")]
    g = MagicMock()
    g.id, g.roles, g.text_channels, g.voice_channels = G, ruoli, testo, voce
    g.get_role = lambda i: next((r for r in ruoli if r.id == i), None)
    g.get_channel = lambda i: next((c for c in testo + voce if c.id == i), None)
    return g


@pytest.fixture
async def guild(monkeypatch, clean_db):
    monkeypatch.setattr(database_module.db, "_pool", clean_db)
    await db.ensure_guild_exists(G)
    return _guild()


def test_ogni_chiave_delle_schede_e_nello_schema_con_un_controllo():
    storia = ci._storia()
    for nome, campi in ci.SCHEDE.items():
        for c in campi:
            assert c.chiave in storia.SETTINGS_SCHEMA, (nome, c.chiave)
            assert storia.SETTINGS_SCHEMA[c.chiave] in storia.CONTROLLI_PER_TIPO
            if c.tipo == ci.SCELTA:
                assert ci._scelte(storia.SETTINGS_SCHEMA[c.chiave]), c.chiave


def test_riservate_al_proprietario_non_compaiono():
    storia = ci._storia()
    tutte = {c.chiave for nome in ci.SCHEDE for c in ci.campi_modulo(nome)}
    assert not tutte & set(storia.CHIAVI_SOLO_PROPRIETARIO)
    assert ci.campi_modulo("inesistente") == ()


async def test_valori_con_opzioni(guild):
    await db.set_guild_setting(G, "verify_captcha_tipo", "immagine")
    righe = {r["chiave"]: r for r in await ci.valori_modulo(guild, "verify")}
    assert righe["verify_captcha_tipo"]["valore"] == "immagine" and righe["verify_captcha_tipo"]["scelte"] == ("testo", "immagine")
    assert righe["verify_unverified_role_id"]["opzioni"] == [(11, "Mod")]  # niente @everyone né ruoli dei bot
    musica = {r["chiave"]: r for r in await ci.valori_modulo(guild, "music")}
    assert musica["music_allowed_voice_channel_id"]["opzioni"] == [(31, "Musica")]
    assert [r["chiave"] for r in await ci.valori_modulo(guild, "suggestions")][0] == "suggestions_channel_id"


async def test_scrive_con_storico_e_non_riscrive_il_uguale(guild):
    assert await ci.imposta_impostazione(guild, "music", "music_max_volume", "150", 9) is True
    assert await db.get_guild_setting(G, "music_max_volume") == 150
    assert await ci.imposta_impostazione(guild, "music", "music_max_volume", "150", 9) is False
    assert await ci.imposta_impostazione(guild, "music", "music_stay_when_queue_ends", "1", 9) is True
    assert await db.get_guild_setting(G, "music_stay_when_queue_ends") is True


async def test_canale_e_ruolo_devono_esistere_e_vuoto_toglie(guild):
    assert await ci.imposta_impostazione(guild, "moderation_report", "report_channel_id", "21", 9)
    assert await db.get_guild_setting(G, "report_channel_id") == 21
    for storto in ("999", "abc", str(G)):
        with pytest.raises(ImpostazioneNonValida):
            await ci.imposta_impostazione(guild, "moderation_report", "report_channel_id", storto, 9)
    assert await ci.imposta_impostazione(guild, "moderation_report", "report_channel_id", "", 9)
    assert await db.get_guild_setting(G, "report_channel_id") is None
    assert await ci.imposta_impostazione(guild, "tickets", "ticket_support_role_id", "11", 9)
    with pytest.raises(ImpostazioneNonValida):
        await ci.imposta_impostazione(guild, "tickets", "ticket_support_role_id", "22", 9)  # un canale non è un ruolo


@pytest.mark.parametrize("modulo,chiave,valore", [
    ("music", "music_max_volume", "201"), ("music", "music_max_volume", "x"), ("music", "music_stay_when_queue_ends", "forse"),
    ("verify", "verify_captcha_tipo", "altro"), ("tickets", "ticket_max_per_utente", "6"),
    ("music", "music_banned_words", "x" * 301), ("automod", "automod_parole_base", "1"),
    ("music", "verify_captcha_tipo", "testo"), ("music", "policy_comandi_off", "x"), ("nessuno", "music_max_volume", "1"),
])
async def test_rifiuta_valori_chiavi_e_moduli_sbagliati(guild, modulo, chiave, valore):
    with pytest.raises(ImpostazioneNonValida):
        await ci.imposta_impostazione(guild, modulo, chiave, valore, 9)
    assert await db.get_guild_setting(G, chiave) is None
