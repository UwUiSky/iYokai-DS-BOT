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
| UTL-048 | sì (da 10 minuti a 30 giorni, ore e giorni esclusi) | sì (minimo 10 minuti e non 5: tetto per la quota dello scheduler) | nessuna | cogs/utility/inneschi.py; tests/test_tag_inneschi.py::test_intervallo, test_escludi |
| UTL-049 | in parte (solo cron scritto a mano) | sì | realizzata: forma guidata «ogni giorno 09:30», «lun, gio 18:00» | core/tag_inneschi_logic.orario_guidato; tests/test_tag_inneschi.py::test_utl_049 |
| UTL-050 | sì (innesco «bottone» di un embed, vista persistente) | sì | nessuna | tests/test_inneschi_cog.py::test_aggiungi_bottone_deve_esistere |
| UTL-051 | sì (moduli di NF-34, `/forms`) | sì | nessuna | cogs/utility/forms.py; tests/test_forms.py::test_invio_consegna_allo_staff_e_registra_il_bottone |
| UTL-052 | sì | sì (tetto 3 tag per evento) | nessuna | tests/test_inneschi_cog.py::test_ruolo_dato_e_tolto |
| UTL-053 | sì (`anche_modificati`, entro 10 minuti) | sì | nessuna | tests/test_custom_commands.py::test_reazioni_e_nuovo_innesco |
| UTL-054 | sì (`avvia-ora`) | sì | nessuna | tests/test_inneschi_cog.py::test_togli_elenco_avvia_ora |
| UTL-056 | sì | sì (mai ai bot, menzioni spente, pausa per canale) | nessuna | cogs/utility/autoresponder.py; tests/test_autoresponder.py::test_risponde_una_volta_senza_ping |
| UTL-057 | sì (modo «esatta») | sì | nessuna | test_trigger_corrisponde |
| UTL-058 | sì (modo «parziale» = parola intera) | sì | nessuna | test_trigger_corrisponde |
| UTL-059 | sì (modo «inizia», `{resto}`) | sì | nessuna | tests/test_risposte_regex_globali.py::test_inizia_con_e_resto |
| UTL-060 | no | sì | realizzata: modo «finisce» (0761) | core/autoresponder_logic.py; tests/test_autoresponder_r2utl.py::test_utl_060 |
| UTL-062 | no | sì | realizzata: opzione `maiuscole`, anche per la regex RE2 | stesso; test_utl_062 |
| UTL-063 | sì (un canale) | sì | nessuna | test_scegli_risposta_rispetta_canale_e_ruolo |
| UTL-064 | no | sì | realizzata: `/admin-tag risposte escludi` (utenti, canali; 10 per elenco) | autoresponder.py; test_utl_064_065, test_utl_064_escludi |
| UTL-065 | in parte (un ruolo richiesto) | sì | realizzata: ruoli esclusi | stesso |
| UTL-066 | no | sì | realizzata: `/admin-tag risposte modifica` (colonne da elenco fisso, `{resto}` controllato) | autoresponder_repo.modifica; test_utl_066 |
| UTL-067 | in parte (solo elenco) | sì | realizzata: `/admin-tag risposte mostra` con testo grezzo, menzioni spente | test_utl_067 |
| UTL-070 | no | sì | realizzata: innesco `canale_testo` (0763), ignora bot e messaggi di sistema, argomento tagliato a 200, pausa minima dell'innesco | cogs/utility/inneschi.py; tests/test_inneschi_cog.py::test_utl_070_* |
| UTL-073 | sì | sì (limiti 256/4096/1024/25/6000, indirizzi da safe_http) | nessuna | cogs/utility/embed_builder.py; tests/test_embed_builder.py::test_crea_salva_e_mostra_l_anteprima |
| UTL-074 | in parte (mancavano autore, link, data) | sì | realizzata: `autore`, `link`, `data` in crea e modifica | core/embed_builder_logic.py; tests/test_embed_r2utl.py::test_utl_074 |
| UTL-077 | sì (embed pubblicato del bot, prima Discord poi database) | sì | nessuna | test_modifica_aggiorna_il_messaggio_gia_pubblicato_prima_di_salvare |
| UTL-078 | sì | sì | nessuna | test_salva_leggi_elenca_elimina |
| UTL-082 | sì (anteprima privata) | sì | nessuna | test_crea_salva_e_mostra_l_anteprima |
| UTL-084 | no | sì | realizzata: `/admin-messaggi embed colore` (0762), vale solo se l'embed non ha il suo | saved_embed_repo; tests/test_embed_r2utl.py::test_utl_084_* |
| UTL-085 | no | sì | realizzata: un invio al minuto per server in `pubblica` | embed_builder.py; test_utl_085 |
