"""
tests/test_backup_modelli.py
============================
Modelli di server: pronti nel bot, lettura per nome, codice o link discord.new, elenco e scheda.
Funzioni coperte: BKP-020, BKP-021, BKP-022
"""

from __future__ import annotations

from unittest.mock import MagicMock

import discord

from core import backup_modelli_logic as modelli
from core import backup_struttura_logic as st


def _modello_discord():
    dati = {
        "code": "abcDEF1234", "name": "Test", "description": "d", "usage_count": 3, "creator_id": "5",
        "creator": {"id": "5", "username": "u", "discriminator": "0", "avatar": None},
        "created_at": "2020-01-01T00:00:00+00:00", "updated_at": "2020-01-01T00:00:00+00:00",
        "source_guild_id": "77", "is_dirty": None,
        "serialized_source_guild": {
            "name": "Src", "description": None, "region": "us", "verification_level": 1,
            "default_message_notifications": 0, "explicit_content_filter": 0, "preferred_locale": "en-US",
            "afk_timeout": 300, "afk_channel_id": None, "system_channel_id": None, "system_channel_flags": 0,
            "roles": [
                {"id": 0, "name": "@everyone", "permissions": "1071698660929", "color": 0, "hoist": False,
                 "mentionable": False, "position": 0, "managed": False, "flags": 0},
                {"id": 1, "name": "Mod", "permissions": "8", "color": 255, "hoist": True,
                 "mentionable": False, "position": 1, "managed": False, "flags": 0},
            ],
            "channels": [
                {"id": 2, "type": 4, "name": "Info", "position": 0, "permission_overwrites": []},
                {"id": 3, "type": 0, "name": "regole", "position": 1, "topic": "x", "nsfw": False,
                 "rate_limit_per_user": 0, "parent_id": 2,
                 "permission_overwrites": [{"id": 1, "type": 0, "allow": "1024", "deny": "0"}]},
                {"id": 4, "type": 2, "name": "voce", "position": 2, "bitrate": 64000, "user_limit": 0,
                 "parent_id": None, "permission_overwrites": []},
            ],
        },
    }
    return discord.Template(state=MagicMock(), data=dati)


def test_i_modelli_pronti_sono_validi_e_senza_permessi_pericolosi():
    """BKP-022: pochi modelli pronti nel bot; nessuno porta permessi pericolosi né dati personali."""
    assert len(modelli.MODELLI_PRONTI) >= 3
    for chiave, m in modelli.MODELLI_PRONTI.items():
        assert st.valida_struttura(m["dati"]) == [], chiave
        assert st.senza_dati_personali(m["dati"])["ruoli"] == m["dati"]["ruoli"]
        for r in m["dati"]["ruoli"]:
            assert not r["permessi"] & st.PERMESSI_PERICOLOSI, chiave
        assert not m["dati"]["everyone"] & st.PERMESSI_PERICOLOSI
        assert len(m["descrizione"]) <= 200


def test_trova_pronto_per_chiave_o_titolo():
    assert modelli.trova_pronto("Comunità")[0] == "comunita"
    assert modelli.trova_pronto(" GIOCO ")[0] == "gioco"
    assert modelli.trova_pronto("niente") is None


def test_codice_da_nome_codice_o_link():
    """BKP-020: un link discord.new, discord.com/template o il codice nudo; altri indirizzi no."""
    assert modelli.codice_discord("https://discord.new/abcDEF1234") == "abcDEF1234"
    assert modelli.codice_discord("discord.new/abcDEF1234/") == "abcDEF1234"
    assert modelli.codice_discord("https://discord.com/template/abcDEF1234") == "abcDEF1234"
    assert modelli.codice_discord("abcDEF1234") == "abcDEF1234"
    assert modelli.codice_discord("https://evil.example/abcDEF1234") is None
    assert modelli.codice_discord("a b") is None


def test_modello_di_discord_diventa_struttura_senza_dati_personali():
    esito = modelli.da_modello_discord(_modello_discord())
    assert esito is not None
    nome, dati = esito
    assert nome == "Test"
    assert [r["nome"] for r in dati["ruoli"]] == ["Mod"]
    assert {c["nome"] for c in dati["canali"]} == {"regole", "voce"}
    assert dati["canali"][0]["categoria"] == "Info"
    assert "ban" not in dati and "membri" not in dati
    assert st.valida_struttura(dati) == []


def test_modello_illeggibile_da_none():
    rotto = MagicMock()
    rotto.source_guild = None
    assert modelli.da_modello_discord(rotto) is None
