# Controllo delle aree chiuse

Una sezione per area, scritta dall'agente che la controlla. Colonne: codice, esiste, corretta (e cosa non va), azione, file e test.

## 14-utility

Giro r2utl (issue #128). «Corretta» = fa ciò che dice il catalogo e rispetta SICUREZZA.md.

| codice | esiste | corretta | azione | file e test |
|---|---|---|---|---|
| UTL-001 | sì | sì | nessuna (codice nel test) | cogs/utility/custom_commands.py; tests/test_custom_commands.py::test_crea_ok_salva_ping_ruoli_secondo_i_permessi |
| UTL-002 | sì (opzioni, non finestra col testo attuale) | sì | nessuna | custom_commands.py `modifica`; test_modifica_cambia_solo_i_campi_dati |
| UTL-003 | no | sì | realizzata: opzione `in_coda` di `/admin-tag tag modifica`, UPDATE atomico entro 4000, il ping dei ruoli non cresce | custom_command_repo.aggiungi_in_coda; tests/test_tag_extra_r2utl.py::test_utl_003 |
| UTL-004 | sì | sì | nessuna | test_crea_leggi_elenca_elimina; tests/test_tag_eliminazione.py |
| UTL-005 | sì | sì (elenco tagliato a 3800 caratteri, tetto 50 tag; completamento a 25) | nessuna | custom_commands.py `elenco`; test_crea_leggi_elenca_elimina |
| UTL-006 | sì | sì (% e _ trattati come testo) | nessuna | test_search_names_tratta_percento_e_trattino_basso_come_testo |
| UTL-007 | no | sì | realizzata: `/admin-tag tag info grezzo:sì`, blocco di codice, menzioni neutre | cogs/utility/tag_extra.py; test_grezzo_non_chiude_il_blocco_e_non_pinga, test_utl_008 |
| UTL-008 | in parte (solo conteggio usi) | sì | realizzata: scheda con autore, usi, alias | tag_extra.py `info`; test_utl_008 |
| UTL-009 | no | sì | realizzata: tabella tag_alias (0760), 3 per tag, nomi unici per server, usati da `/tag usa` e dal prefisso | custom_command_repo; tag_extra.py `alias`; test_utl_009 |
| UTL-010 | sì (risposte con peso) | sì | nessuna | test_risposte_con_peso_e_testo_lungo |
| UTL-012 | in parte (solo per utente) | sì | realizzata: colonna pausa_ambito (utente, canale, server) in `/admin-tag tag opzioni` | custom_commands.py `_pausa`; test_utl_012 |
| UTL-013 | sì (gruppi: un canale e un ruolo) | sì | nessuna | test_tag_gestione.py::test_gruppo_regole_di_canale_e_ruolo |
| UTL-014 | no | sì | realizzata: elenchi di ruoli, canali, utenti vietati (10 per elenco), thread inclusi | core/custom_command_logic.vietato_a; tag_extra.py `divieti`; test_utl_014 |
| UTL-016 | sì | sì (ruolo controllato con check_role_assignable) | nessuna | test_tag_con_ruolo_lo_da |
| UTL-018 | in parte (solo testo come embed) | sì | realizzata: opzione `embed` collega un embed salvato (se sparisce risponde col testo) | tag_opzioni.py; custom_commands._manda; test_utl_018 |
| UTL-022 | sì | sì | nessuna | test_risposta_con_reazioni_e_cancellazione_prenotata |
| UTL-023 | sì (scheduler) | sì | nessuna | stesso test |
| UTL-025 | sì (`cancella_messaggi`, serve «Gestire i messaggi» a chi lo usa, 14 giorni) | sì | nessuna | test_pulizia_solo_con_il_permesso_e_modifica_solo_se_richiesta |
| UTL-026 | sì | sì (args = dati, menzioni spente) | nessuna | test_uso_con_slash_risponde_con_testo_senza_ping |
| UTL-028 | sì | sì (tetti, niente eval) | nessuna | tests/test_tag_script_logic.py::test_variabili_e_contesto |
| UTL-029 | sì | sì | nessuna | test_calcola |
| UTL-030 | sì | sì | nessuna | test_maiuscole_sostituisci_lunghezza |
| UTL-031 | sì | sì | nessuna | test_data_e_tra |
| UTL-033 | sì (4000 caratteri, diviso in messaggi da 2000) | sì | nessuna | test_risposte_con_peso_e_testo_lungo |
| UTL-036 | sì (/admin-tag richiede «Gestire il server») | sì | nessuna | test_tag_extra_r2utl.py::test_utl_036 |
| UTL-038 | in parte (invio «altro» senza ping) | sì | realizzata: la risposta nell'altro canale comincia con la menzione di chi ha usato il tag | custom_commands._manda; test_utl_038 |
