"""
tests/test_role_menu_logic.py
================================
Test di core/role_menu_logic.py — logica pura, nessuna dipendenza da
Discord. Il caso più importante: compute_select_sync() non deve mai
toccare un ruolo del membro che non appartiene al menu.
"""

from core.role_menu_logic import (
    MODE_MAX_OPTIONS,
    can_add_option,
    compute_select_sync,
    compute_toggle_action,
)


class TestCanAddOption:
    def test_sotto_il_limite_reaction(self):
        assert can_add_option(current_option_count=5, mode="reaction") is True

    def test_al_limite_reaction(self):
        limite = MODE_MAX_OPTIONS["reaction"]
        assert can_add_option(current_option_count=limite, mode="reaction") is False

    def test_appena_sotto_il_limite_button(self):
        limite = MODE_MAX_OPTIONS["button"]
        assert can_add_option(current_option_count=limite - 1, mode="button") is True

    def test_al_limite_select(self):
        limite = MODE_MAX_OPTIONS["select"]
        assert can_add_option(current_option_count=limite, mode="select") is False

    def test_modalita_sconosciuta_usa_limite_di_default(self):
        # Non dovrebbe mai capitare con le tre modalità note, ma la
        # funzione non deve sollevare per un valore imprevisto.
        assert can_add_option(current_option_count=0, mode="qualcosa_altro") is True


class TestComputeToggleAction:
    def test_membro_senza_ruolo_lo_aggiunge(self):
        assert compute_toggle_action(member_has_role=False) == "add"

    def test_membro_con_ruolo_lo_rimuove(self):
        assert compute_toggle_action(member_has_role=True) == "remove"


class TestComputeSelectSync:
    def test_selezione_da_zero_aggiunge_tutto(self):
        aggiungere, rimuovere = compute_select_sync(
            current_member_role_ids=set(),
            menu_role_ids={1, 2, 3},
            selected_role_ids={1, 2},
        )
        assert aggiungere == {1, 2}
        assert rimuovere == set()

    def test_deselezione_rimuove_solo_quello_tolto(self):
        aggiungere, rimuovere = compute_select_sync(
            current_member_role_ids={1, 2},
            menu_role_ids={1, 2, 3},
            selected_role_ids={1},
        )
        assert aggiungere == set()
        assert rimuovere == {2}

    def test_non_tocca_mai_ruoli_fuori_dal_menu(self):
        # Il caso più importante: il membro ha un ruolo di moderazione
        # (99) che non fa parte di questo menu — non deve MAI comparire
        # né in aggiungere né in rimuovere, qualunque cosa selezioni.
        aggiungere, rimuovere = compute_select_sync(
            current_member_role_ids={1, 99},
            menu_role_ids={1, 2, 3},
            selected_role_ids={2, 3},
        )
        assert 99 not in aggiungere
        assert 99 not in rimuovere
        assert aggiungere == {2, 3}
        assert rimuovere == {1}

    def test_selezione_identica_a_quella_attuale_nessun_cambiamento(self):
        aggiungere, rimuovere = compute_select_sync(
            current_member_role_ids={1, 2},
            menu_role_ids={1, 2, 3},
            selected_role_ids={1, 2},
        )
        assert aggiungere == set()
        assert rimuovere == set()

    def test_deselezione_totale_rimuove_tutti_i_ruoli_del_menu_posseduti(self):
        aggiungere, rimuovere = compute_select_sync(
            current_member_role_ids={1, 2, 3},
            menu_role_ids={1, 2, 3},
            selected_role_ids=set(),
        )
        assert aggiungere == set()
        assert rimuovere == {1, 2, 3}

    def test_menu_e_selezione_vuoti(self):
        aggiungere, rimuovere = compute_select_sync(
            current_member_role_ids={1}, menu_role_ids=set(), selected_role_ids=set()
        )
        assert aggiungere == set()
        assert rimuovere == set()
