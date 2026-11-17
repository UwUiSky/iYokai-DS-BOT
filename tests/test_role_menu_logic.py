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


# ------------------------------------------------- RUO-062, RUO-063, RUO-065: limiti del menu
def test_RUO_062_tetto_di_ruoli_anche_per_bottoni_e_reazioni():
    # RUO-062
    from core.role_menu_logic import Decisione, controlla_limiti

    d = Decisione(aggiungi=(3,))
    assert controlla_limiti(d, ruoli_menu={1, 2, 3}, ruoli_membro={1, 2}, massimo=2, minimo=None)
    assert controlla_limiti(d, ruoli_menu={1, 2, 3}, ruoli_membro={1}, massimo=2, minimo=None) is None
    assert controlla_limiti(d, ruoli_menu={1, 2, 3}, ruoli_membro={1, 2}, massimo=None, minimo=None) is None
    # con unique il ruolo vecchio esce: il tetto non scatta
    u = Decisione(aggiungi=(3,), togli=(1,))
    assert controlla_limiti(u, ruoli_menu={1, 3}, ruoli_membro={1}, massimo=1, minimo=None) is None


def test_RUO_063_almeno_un_ruolo_resta():


    # RUO-063
    from core.role_menu_logic import Decisione, controlla_limiti

    d = Decisione(togli=(1,))
    assert controlla_limiti(d, ruoli_menu={1, 2}, ruoli_membro={1}, massimo=None, minimo=1)
    assert controlla_limiti(d, ruoli_menu={1, 2}, ruoli_membro={1, 2}, massimo=None, minimo=1) is None
    # un rifiuto già deciso non si tocca; nessun cambio = nessun controllo
    assert controlla_limiti(Decisione(), ruoli_menu={1}, ruoli_membro={1}, massimo=None, minimo=1) is None


def test_RUO_065_posti_limitati_per_opzione():


    # RUO-065
    from core.role_menu_logic import posti_finiti

    assert posti_finiti(membri_con_ruolo=5, max_membri=5) is True
    assert posti_finiti(membri_con_ruolo=4, max_membri=5) is False
    assert posti_finiti(membri_con_ruolo=99, max_membri=None) is False


# ------------------------------------------------- RUO-048, RUO-049: coppie emoji-ruolo
def test_RUO_048_049_coppie_con_menzioni_id_e_nomi():
    # RUO-048, RUO-049
    from core.role_menu_logic import analizza_coppie

    nomi = {"Gamer": 1111111111111111111}.get
    coppie, errore = analizza_coppie("🎮 <@&2222222222222222222>; 🎨 Gamer\n3333333333333333333", nomi)
    assert errore is None
    assert coppie == [("🎮", 2222222222222222222), ("🎨", 1111111111111111111), (None, 3333333333333333333)]


def test_RUO_048_049_coppie_storte_danno_un_errore():


    # RUO-048, RUO-049
    from core.role_menu_logic import MAX_COPPIE, analizza_coppie

    nessuno = lambda nome: None  # noqa: E731
    assert analizza_coppie("", nessuno)[1]
    assert "Non trovo" in analizza_coppie("🎮 Inventato", nessuno)[1]
    assert "due volte" in analizza_coppie("<@&2222222222222222222>; 🎮 <@&2222222222222222222>", nessuno)[1]
    troppe = ";".join(f"<@&{10**17 + n}>" for n in range(MAX_COPPIE + 1))
    assert "Al massimo" in analizza_coppie(troppe, nessuno)[1]
    assert "troppo lungo" in analizza_coppie("x" * 2000, nessuno)[1]


# ------------------------------------------------- RUO-088, RUO-089: tipo e modelli
def test_RUO_088_conversione_delle_opzioni_tra_i_tipi():
    # RUO-088
    from core.role_menu_logic import converti_opzioni

    nome = {1: "Gamer"}.get
    # reazioni -> bottoni: manca l'etichetta, si usa il nome del ruolo
    assert converti_opzioni([(1, "🎮", None)], "button", nome) == ([("🎮", "Gamer")], None)
    # tendina -> reazioni: senza emoji non si può
    assert "manca l'emoji" in converti_opzioni([(1, None, "Gamer")], "reaction", nome)[1]
    # tendina con emoji -> bottoni va bene
    assert converti_opzioni([(1, "🎮", "G")], "button", nome)[1] is None
    # troppe opzioni per le reazioni (tetto 20)
    assert "al massimo 20" in converti_opzioni([(i, "🎮", "x") for i in range(21)], "reaction", nome)[1]


def test_RUO_089_i_modelli_sono_coerenti_con_i_comportamenti():


    # RUO-089
    from core.role_menu_logic import MODELLI_MENU, comportamento_ammesso

    assert set(MODELLI_MENU) == {"verifica", "notifiche", "colori", "interessi"}
    for modo, comportamento, titolo, _desc, _max, quante in MODELLI_MENU.values():
        assert comportamento_ammesso(modo, comportamento) and titolo and 1 <= quante <= 25
