"""
tests/test_automod_sync.py
=============================
Test di core/automod_sync.py — logica pura, nessuna dipendenza da
Discord o dal database. Il punto più importante da verificare è che
il merge non cancelli MAI nulla di ciò che esisteva già (nemmeno
parole aggiunte a mano dall'admin nel pannello Discord).
"""

from core.automod_sync import (
    DesiredRule,
    ExistingRule,
    SyncActionType,
    compute_sync_plan,
)


class TestComputeSyncPlan:
    def test_regola_inesistente_viene_creata(self):
        piano = compute_sync_plan(
            existing_rules=[],
            desired_rules=[DesiredRule(name="iYokai — Test", keywords=("parola1",))],
        )
        assert len(piano) == 1
        assert piano[0].action == SyncActionType.CREATE
        assert piano[0].final_keywords == ("parola1",)

    def test_regola_desiderata_senza_contenuto_viene_ignorata(self):
        # Nessun contenuto (keywords e regex entrambi vuoti): Discord
        # rifiuterebbe una regola così, non ha senso proporla.
        piano = compute_sync_plan(
            existing_rules=[],
            desired_rules=[DesiredRule(name="iYokai — Vuota")],
        )
        assert piano == []

    def test_regola_esistente_identica_viene_saltata(self):
        piano = compute_sync_plan(
            existing_rules=[ExistingRule(name="iYokai — Test", keywords=("a", "b"))],
            desired_rules=[DesiredRule(name="iYokai — Test", keywords=("a", "b"))],
        )
        assert len(piano) == 1
        assert piano[0].action == SyncActionType.SKIP

    def test_regola_esistente_con_nuove_parole_viene_aggiornata(self):
        piano = compute_sync_plan(
            existing_rules=[ExistingRule(name="iYokai — Test", keywords=("a",))],
            desired_rules=[DesiredRule(name="iYokai — Test", keywords=("b",))],
        )
        assert len(piano) == 1
        assert piano[0].action == SyncActionType.UPDATE
        assert piano[0].final_keywords == ("a", "b")

    def test_parole_esistenti_non_vengono_mai_perse(self):
        # Il caso critico: se un admin ha aggiunto "parola_admin" a
        # mano dal pannello Discord a questa regola, un sync
        # successivo NON deve farla sparire.
        piano = compute_sync_plan(
            existing_rules=[
                ExistingRule(name="iYokai — Test", keywords=("parola_admin", "spam"))
            ],
            desired_rules=[DesiredRule(name="iYokai — Test", keywords=("nuova",))],
        )
        assert set(piano[0].final_keywords) == {"parola_admin", "spam", "nuova"}

    def test_duplicati_non_vengono_aggiunti_due_volte(self):
        piano = compute_sync_plan(
            existing_rules=[ExistingRule(name="iYokai — Test", keywords=("spam",))],
            desired_rules=[DesiredRule(name="iYokai — Test", keywords=("spam", "spam2"))],
        )
        assert piano[0].final_keywords == ("spam", "spam2")

    def test_regola_con_nome_diverso_da_admin_non_viene_toccata(self):
        # Una regola creata dall'admin con un nome che NON inizia per
        # "iYokai — " semplicemente non compare tra le desired_rules
        # (il cog non la propone mai): qui verifichiamo che se per
        # errore comparisse in existing_rules senza un desired
        # corrispondente, il piano non genera nessuna azione su di
        # essa.
        piano = compute_sync_plan(
            existing_rules=[ExistingRule(name="Regola manuale admin", keywords=("x",))],
            desired_rules=[DesiredRule(name="iYokai — Test", keywords=("y",))],
        )
        nomi_toccati = {azione.name for azione in piano}
        assert "Regola manuale admin" not in nomi_toccati

    def test_troncamento_oltre_il_limite_keywords(self):
        esistenti = tuple(f"parola{i}" for i in range(998))
        piano = compute_sync_plan(
            existing_rules=[ExistingRule(name="iYokai — Test", keywords=esistenti)],
            desired_rules=[
                DesiredRule(name="iYokai — Test", keywords=("nuova1", "nuova2", "nuova3"))
            ],
            max_keywords=1000,
        )
        assert len(piano[0].final_keywords) == 1000
        assert piano[0].truncated is True

    def test_nessun_troncamento_sotto_il_limite(self):
        piano = compute_sync_plan(
            existing_rules=[ExistingRule(name="iYokai — Test", keywords=("a",))],
            desired_rules=[DesiredRule(name="iYokai — Test", keywords=("b",))],
            max_keywords=1000,
        )
        assert piano[0].truncated is False

    def test_troncamento_regex(self):
        esistenti = tuple(f"pattern{i}" for i in range(9))
        piano = compute_sync_plan(
            existing_rules=[ExistingRule(name="iYokai — Test", regex_patterns=esistenti)],
            desired_rules=[
                DesiredRule(name="iYokai — Test", regex_patterns=("nuovo1", "nuovo2"))
            ],
            max_regex=10,
        )
        assert len(piano[0].final_regex) == 10
        assert piano[0].truncated is True

    def test_piu_regole_desiderate_generano_piu_azioni_indipendenti(self):
        piano = compute_sync_plan(
            existing_rules=[ExistingRule(name="iYokai — Badwords", keywords=("a",))],
            desired_rules=[
                DesiredRule(name="iYokai — Badwords", keywords=("b",)),
                DesiredRule(name="iYokai — Anti-Invite", regex_patterns=(r"discord\.gg/\S+",)),
            ],
        )
        assert len(piano) == 2
        azioni_per_nome = {a.name: a for a in piano}
        assert azioni_per_nome["iYokai — Badwords"].action == SyncActionType.UPDATE
        assert azioni_per_nome["iYokai — Anti-Invite"].action == SyncActionType.CREATE


class TestRimozioneParoleTraTreVie:
    """
    Il caso che ha richiesto il merge a tre vie: una parola che
    iYokai stesso aveva sincronizzato in passato deve poter
    SPARIRE dalla regola Discord quando l'admin la rimuove dalla
    configurazione (/automod badword-remove) — ma senza intaccare
    parole che l'admin ha aggiunto direttamente dal pannello Discord.
    """

    def test_parola_rimossa_da_iyokai_sparisce_dalla_regola(self):
        # "a" era stata scritta da iYokai in un sync precedente
        # (previously_synced_keywords) ed è quindi ancora presente
        # nella regola live (existing). Ora l'admin l'ha rimossa
        # dalla configurazione (desired.keywords non la contiene
        # più): deve sparire dal risultato finale.
        piano = compute_sync_plan(
            existing_rules=[ExistingRule(name="iYokai — Test", keywords=("a", "b"))],
            desired_rules=[
                DesiredRule(
                    name="iYokai — Test",
                    keywords=("b",),  # "a" non c'è più: è stata rimossa
                    previously_synced_keywords=("a", "b"),  # entrambe erano nostre
                )
            ],
        )
        assert piano[0].final_keywords == ("b",)
        assert "a" not in piano[0].final_keywords

    def test_parola_aggiunta_dallo_admin_sopravvive_alla_rimozione_di_unaltra(self):
        # "manuale" non è mai stata scritta da iYokai (non compare in
        # previously_synced_keywords): è dell'admin, deve restare
        # anche se contemporaneamente iYokai rimuove una SUA parola.
        piano = compute_sync_plan(
            existing_rules=[
                ExistingRule(name="iYokai — Test", keywords=("a", "manuale"))
            ],
            desired_rules=[
                DesiredRule(
                    name="iYokai — Test",
                    keywords=(),  # iYokai non vuole più nessuna parola sua
                    previously_synced_keywords=("a",),  # solo "a" era nostra
                )
            ],
        )
        assert piano[0].final_keywords == ("manuale",)

    def test_senza_previously_synced_tutto_e_trattato_come_admin(self):
        # Comportamento di sicurezza per una regola mai tracciata
        # prima (es. bot appena aggiornato con questa funzionalità):
        # previously_synced vuoto -> tutto il contenuto esistente
        # viene preservato, esattamente come il vecchio comportamento
        # "solo unione" - retrocompatibile con i test scritti prima
        # dell'introduzione del merge a tre vie.
        piano = compute_sync_plan(
            existing_rules=[ExistingRule(name="iYokai — Test", keywords=("x", "y"))],
            desired_rules=[DesiredRule(name="iYokai — Test", keywords=("z",))],
        )
        assert set(piano[0].final_keywords) == {"x", "y", "z"}

    def test_rimozione_completa_di_tutte_le_parole_iyokai(self):
        # Se TUTTE le parole erano nostre e vengono tutte rimosse
        # dalla configurazione, e l'admin non ne ha aggiunte di sue,
        # non resta nulla da tenere: la regola va ELIMINATA, non
        # aggiornata a vuoto (Discord rifiuta una regola keyword
        # senza contenuto).
        piano = compute_sync_plan(
            existing_rules=[ExistingRule(name="iYokai — Test", keywords=("a", "b"))],
            desired_rules=[
                DesiredRule(
                    name="iYokai — Test",
                    keywords=(),
                    previously_synced_keywords=("a", "b"),
                )
            ],
        )
        assert piano[0].action == SyncActionType.DELETE
        assert piano[0].final_keywords == ()
