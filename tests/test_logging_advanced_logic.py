"""
tests/test_logging_advanced_logic.py
=========================================
Test della logica pura del Logging Avanzato (SPEC.md §8.6-§8.15,
core/logging_advanced_logic.py) — nessun database, nessun discord.py.
"""

from core.logging_advanced_logic import (
    CHANNEL_TRACKED_KEYS,
    GUILD_TRACKED_KEYS,
    ROLE_TRACKED_KEYS,
    classify_voice_state_change,
    diff_attributes,
    diff_id_sets,
    diff_named_items,
)


class TestDiffAttributes:
    def test_nessun_cambiamento_restituisce_dizionario_vuoto(self):
        before = {"name": "Mod", "color": 1}
        after = {"name": "Mod", "color": 1}
        assert diff_attributes(before, after, ROLE_TRACKED_KEYS) == {}

    def test_un_solo_attributo_cambiato_viene_riportato(self):
        before = {"name": "Mod", "color": 1, "hoist": False, "mentionable": False, "permissions": 0}
        after = {"name": "Moderatore", "color": 1, "hoist": False, "mentionable": False, "permissions": 0}
        risultato = diff_attributes(before, after, ROLE_TRACKED_KEYS)
        assert risultato == {"name": {"before": "Mod", "after": "Moderatore"}}

    def test_piu_attributi_cambiati_insieme(self):
        before = {"name": "general", "category_id": 1, "topic": None, "nsfw": False, "slowmode_delay": 0, "position": 0}
        after = {"name": "general-chat", "category_id": 1, "topic": None, "nsfw": True, "slowmode_delay": 0, "position": 0}
        risultato = diff_attributes(before, after, CHANNEL_TRACKED_KEYS)
        assert set(risultato.keys()) == {"name", "nsfw"}

    def test_attributi_non_tracciati_vengono_ignorati(self):
        before = {"name": "Server", "irrilevante": 1}
        after = {"name": "Server", "irrilevante": 2}
        assert diff_attributes(before, after, GUILD_TRACKED_KEYS) == {}


class TestDiffIdSets:
    def test_aggiunti_e_rimossi(self):
        added, removed = diff_id_sets({1, 2, 3}, {2, 3, 4})
        assert added == {4}
        assert removed == {1}

    def test_nessun_cambiamento(self):
        added, removed = diff_id_sets({1, 2}, {1, 2})
        assert added == set()
        assert removed == set()


class TestDiffNamedItems:
    def test_emoji_creata(self):
        risultato = diff_named_items({}, {10: "pepe"})
        assert risultato["created"] == [{"id": 10, "name": "pepe"}]
        assert risultato["deleted"] == []
        assert risultato["renamed"] == []

    def test_emoji_eliminata(self):
        risultato = diff_named_items({10: "pepe"}, {})
        assert risultato["deleted"] == [{"id": 10, "name": "pepe"}]

    def test_emoji_rinominata_non_e_elimina_piu_crea(self):
        risultato = diff_named_items({10: "pepe"}, {10: "pepe_v2"})
        assert risultato["created"] == []
        assert risultato["deleted"] == []
        assert risultato["renamed"] == [{"id": 10, "before": "pepe", "after": "pepe_v2"}]

    def test_nessun_cambiamento_tutte_liste_vuote(self):
        risultato = diff_named_items({10: "pepe"}, {10: "pepe"})
        assert risultato == {"created": [], "deleted": [], "renamed": []}

    def test_mix_creata_eliminata_rinominata_insieme(self):
        prima = {1: "a", 2: "b"}
        dopo = {2: "b2", 3: "c"}
        risultato = diff_named_items(prima, dopo)
        assert risultato["created"] == [{"id": 3, "name": "c"}]
        assert risultato["deleted"] == [{"id": 1, "name": "a"}]
        assert risultato["renamed"] == [{"id": 2, "before": "b", "after": "b2"}]


class TestClassifyVoiceStateChange:
    def test_join_canale_vocale(self):
        eventi = classify_voice_state_change({"channel_id": None, "mute": False, "deaf": False}, {"channel_id": 1, "mute": False, "deaf": False})
        assert eventi == ["voice_join"]

    def test_leave_canale_vocale(self):
        eventi = classify_voice_state_change({"channel_id": 1, "mute": False, "deaf": False}, {"channel_id": None, "mute": False, "deaf": False})
        assert eventi == ["voice_leave"]

    def test_move_tra_due_canali(self):
        eventi = classify_voice_state_change({"channel_id": 1, "mute": False, "deaf": False}, {"channel_id": 2, "mute": False, "deaf": False})
        assert eventi == ["voice_move"]

    def test_mute_e_unmute(self):
        assert classify_voice_state_change(
            {"channel_id": 1, "mute": False, "deaf": False}, {"channel_id": 1, "mute": True, "deaf": False}
        ) == ["voice_mute"]
        assert classify_voice_state_change(
            {"channel_id": 1, "mute": True, "deaf": False}, {"channel_id": 1, "mute": False, "deaf": False}
        ) == ["voice_unmute"]

    def test_deafen_e_undeafen(self):
        assert classify_voice_state_change(
            {"channel_id": 1, "mute": False, "deaf": False}, {"channel_id": 1, "mute": False, "deaf": True}
        ) == ["voice_deafen"]
        assert classify_voice_state_change(
            {"channel_id": 1, "mute": False, "deaf": True}, {"channel_id": 1, "mute": False, "deaf": False}
        ) == ["voice_undeafen"]

    def test_nessun_cambiamento_lista_vuota(self):
        stato = {"channel_id": 1, "mute": False, "deaf": False}
        assert classify_voice_state_change(stato, dict(stato)) == []

    def test_move_e_mute_insieme_nello_stesso_evento(self):
        eventi = classify_voice_state_change(
            {"channel_id": 1, "mute": False, "deaf": False}, {"channel_id": 2, "mute": True, "deaf": False}
        )
        assert eventi == ["voice_move", "voice_mute"]
