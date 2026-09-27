"""
tests/test_logging_advanced_logic.py
=========================================
Test della logica pura del Logging Avanzato (SPEC.md §8.6-§8.15,
core/logging_advanced_logic.py) — nessun database, nessun discord.py.
"""

from datetime import datetime, timedelta, timezone

from core.logging_advanced_logic import (
    CHANNEL_TRACKED_KEYS,
    GUILD_TRACKED_KEYS,
    ROLE_TRACKED_KEYS,
    classify_voice_state_change,
    diff_attributes,
    diff_id_sets,
    diff_named_items,
    new_entries_since,
    next_watermark,
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


def _t(secondi_fa: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(seconds=secondi_fa)


class TestNewEntriesSince:
    def test_since_none_restituisce_sempre_vuoto_anche_con_voci_presenti(self):
        # Prima attivazione del modulo: non si riversa lo storico.
        voci = [{"created_at": _t(5)}, {"created_at": _t(1)}]
        assert new_entries_since(voci, None) == []

    def test_filtra_solo_le_voci_piu_recenti_del_watermark(self):
        watermark = _t(10)
        vecchia = {"created_at": _t(20)}
        nuova = {"created_at": _t(2)}
        risultato = new_entries_since([vecchia, nuova], watermark)
        assert risultato == [nuova]

    def test_ordina_dalla_piu_vecchia_alla_piu_nuova(self):
        watermark = _t(100)
        a = {"created_at": _t(5), "id": "a"}
        b = {"created_at": _t(50), "id": "b"}
        c = {"created_at": _t(20), "id": "c"}
        risultato = new_entries_since([a, b, c], watermark)
        assert [r["id"] for r in risultato] == ["b", "c", "a"]

    def test_nessuna_voce_nuova_restituisce_vuoto(self):
        watermark = _t(1)
        vecchia = {"created_at": _t(50)}
        assert new_entries_since([vecchia], watermark) == []


class TestNextWatermark:
    def test_nessuna_voce_mantiene_il_watermark_attuale(self):
        attuale = _t(10)
        assert next_watermark([], attuale) == attuale

    def test_nessuna_voce_e_nessun_watermark_resta_none(self):
        assert next_watermark([], None) is None

    def test_prima_attivazione_stabilisce_la_base_dalla_voce_piu_recente(self):
        piu_recente = _t(1)
        voci = [{"created_at": _t(5)}, {"created_at": piu_recente}]
        assert next_watermark(voci, None) == piu_recente

    def test_avanza_solo_se_la_voce_e_piu_recente_del_watermark_attuale(self):
        attuale = _t(10)
        voci = [{"created_at": _t(50)}]  # più vecchia del watermark
        assert next_watermark(voci, attuale) == attuale

    def test_avanza_al_massimo_tra_le_voci_lette(self):
        attuale = _t(100)
        piu_recente = _t(1)
        voci = [{"created_at": _t(30)}, {"created_at": piu_recente}]
        assert next_watermark(voci, attuale) == piu_recente
