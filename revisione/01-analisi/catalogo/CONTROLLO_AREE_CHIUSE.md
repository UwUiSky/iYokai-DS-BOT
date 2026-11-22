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
| UTL-086 | sì (10 opzioni, sondaggio nativo) | sì | nessuna | cogs/utility/poll.py; tests/test_poll_cog_smoke.py::test_poll_con_dieci_opzioni_crea_dieci_risposte |
| UTL-101 | in parte (solo tempo relativo) | sì | realizzata: elenco con data esatta e relativa | cogs/utility/reminders.py; tests/test_promemoria_catalogo.py::test_utl_101 |
| (difetto trovato) | promemoria ripetuto nel canale | no: il messaggio pubblico non diceva che si ripete | aggiornata: riga «Si ripete ogni…» (lingua del server); test del giro riparati (payload mancante) | reminders.py; tests/test_promemoria_catalogo.py |
| UTL-110 | in parte (ping di ruolo sì, everyone/here muti) | sì | non fattibile D100 (everyone e here mai, D12) | DECISIONI.md D100 |
| UTL-114 | no | sì | realizzata: `/admin-giveaway chiudi` (scadenza a ora, estrae il worker) | cogs/utility/giveaway_extra.py; tests/test_giveaway_extra.py::test_utl_114_117_118_* |
| UTL-115 | sì (menu «Riestrai giveaway», solo staff) | sì | nessuna (alternativa al comando: menu sul messaggio) | test_riestrai_solo_su_annuncio_finito_e_ripesca |
| UTL-117 | in parte (solo programmati) | sì | realizzata: `/admin-giveaway annulla` (senza vincitori, annuncio aggiornato) | giveaway_extra.py; stesso test |
| UTL-118 | in parte (solo programmati) | sì | realizzata: `/admin-giveaway elenco` | stesso |
| UTL-121 | in parte (comando con opzioni) | sì | non fattibile D100 (alternativa più completa) | DECISIONI.md D100 |
| UTL-122 | sì | sì (tetto 25) | nessuna | tests/test_giveaway_avanzati.py::test_modelli_salva_aggiorna_elenca_elimina |
| UTL-123 | sì | sì | nessuna | test_giveaway_programmato_non_posta_subito |
| UTL-124 | sì | sì | nessuna | test_requisito_sui_messaggi |
| UTL-125 | sì | sì | nessuna | test_il_ruolo_bypass_salta_tutti_i_requisiti |
| UTL-127 | sì | sì | nessuna | test_biglietti_extra_solo_con_il_ruolo |
| UTL-143 | sì | sì (permessi del bot nel canale controllati) | nessuna | cogs/utility/starboard.py; tests/test_starboard.py::test_comando_imposta_passa_nsfw_e_voto_autore |
| UTL-144 | sì | sì | nessuna | stesso |
| UTL-145 | sì | sì (di base esclusi) | nessuna | stesso; test_canale_nsfw_escluso_di_default |
| UTL-146 | in parte (solo NSFW e privati) | sì | realizzata: `/admin-moduli starboard esclusi` (0764, 25 canali, thread inclusi) | starboard.py; tests/test_starboard.py::test_utl_146_* |
| UTL-147 | sì | sì (emoji validata) | nessuna | test_comando_imposta_rifiuta_emoji_non_valida |
| UTL-150 | sì (`caso`, link nel post) | sì | nessuna | tests/test_starboard_bacheca.py::test_caso_manda_il_link_al_post |
| UTL-153 | in parte (solo disattiva) | sì | realizzata: `/admin-moduli starboard stato` | tests/test_starboard.py::test_utl_153 |
| UTL-156 | sì | sì (niente anno) | nessuna | cogs/utility/birthdays.py; tests/test_birthdays.py::test_imposta_valida_la_data |
| UTL-157 | sì | sì | nessuna | test_rimuovi_cancella_il_dato |
| UTL-161 | sì | sì (permessi e ruolo assegnabile controllati) | nessuna | test_ruolo_non_assegnabile_rifiutato_alla_configurazione |
| UTL-162 | no | sì | realizzata: `/admin-moduli compleanni stato` | tests/test_birthdays.py::test_utl_162 |
| UTL-163 | sì (`/level inviti utente`) | sì (l'attribuzione può mancare: avviso sempre) | nessuna | cogs/utility/invites.py; tests/test_invites.py::test_comando_storico_e_utente_dicono_da_chi_e_stato_invitato |
| UTL-164 | in parte (solo da sempre; esclusi per utente e ruolo sì) | sì | realizzata: opzione `giorni` (1-365) | invites.py; tests/test_inviti_bonus_esclusi.py::test_utl_164 |
| UTL-165 | sì (`storico`) | sì | nessuna | stesso test di UTL-163 |
| UTL-168 | sì (presenti, usciti, finti, bonus) | sì | nessuna | tests/test_inviti_bonus_esclusi.py::test_finti_non_contano_ma_si_vedono |
| UTL-177 | sì (canale del registro, senza menzioni) | sì | nessuna (nessun ping, per scelta) | tests/test_invites.py::test_registro_scrive_nel_canale_scelto_senza_menzioni |
| UTL-185 | sì | sì | nessuna | cogs/utility/conteggio.py; tests/test_conteggio.py::test_register_giusto_sbagliato_e_punteggi |
| UTL-196 | no | sì | realizzata: `/utility strumenti avatar` (server o globale, 1024 punti, nome senza markdown) | cogs/utility/strumenti_rapidi.py; tests/test_strumenti_rapidi.py::test_utl_196_* |
| UTL-204 | no | - | non è mio: `/mod esporta-chat` sta in moderazione (nota in D100) | - |
| UTL-205 | no | - | non è mio: `cogs/utility/snipe.py` è di altro agente (nota in D100) | - |
| UTL-216 | in parte (`/fun search-image`) | - | non fattibile D100 | DECISIONI.md D100 |
| UTL-223 | sì (`/admin-bot canali`, `ignora`) | sì | nessuna | cogs/utility/politica.py; tests/test_politica_comandi.py::test_canali_ignora_ed_elenco |
| UTL-224 | sì (`/admin-bot comando`) | sì | nessuna | test_comando_spegne_riaccende_e_rifiuta_i_nomi_sbagliati |
| UTL-225 | sì (risposta effimera) | sì | nessuna | test_il_controllo_dell_albero_ferma_il_comando_spento_e_risponde_effimero |
| UTL-226 | no | - | non è mio: `config_history.py` (nota in D100) | - |
| UTL-227 | sì (`ruolo-richiesto`) | sì | nessuna | test_cfg012_serve_uno_dei_ruoli_richiesti_per_il_comando_e_il_suo_gruppo |
| UTL-228 | in parte | - | non è mio: `config_history.py` (nota in D100) | - |

## 01-moderazione

Giro r2mod (issue #115, #116, #118). «Corretta» = fa ciò che dice il catalogo e rispetta SICUREZZA.md (gerarchia, permessi riletti, motivi entro 512, menzioni spente).

| codice | esiste | corretta | azione | file e test |
|---|---|---|---|---|
| MOD-008 | no | sì | realizzata: `appello: no` su ban, tempban e timeout; caso segnato (0800), niente bottone, appello rifiutato | cogs/moderation/actions.py, ban_appeal.py; tests/test_catalogo_r2mod_appelli.py |
| MOD-016 | no | - | NON FATTA: manca `/mod-canali quarantena` (riuso del ruolo dell'anti-raid, ruoli salvati) | resta aperta in #115 |
| MOD-018 | no (il ruolo nasceva solo da solo) | sì | realizzata: `/mod-sanzioni opzioni muto ruolo:\|nome_nuovo:`; il ruolo deve stare sotto il bot e sotto chi comanda, non gestito, senza permessi pericolosi | cogs/moderation/opzioni.py; tests/test_catalogo_r2mod_mute.py |
| MOD-019 | no | sì | realizzata: `muto aggiorna:` rimette il blocco su fino a 500 canali, a gruppi di 8 con pausa | softban_mute.aggiorna_ruolo_muto; tests/test_catalogo_r2mod_mute.py |
| MOD-020 | sì (`add_reactions` già negato) | sì | test aggiunto | softban_mute.MUTE_OVERWRITE; tests/test_catalogo_r2mod_mute.py |
| MOD-032 | sì (`conta_warn_manuali`) | sì (gerarchia e permessi del moderatore, in massa mai kick/ban) | segnata | tests/test_escalation_warn_manuali.py::test_tre_warn_manuali_fanno_scattare_il_gradino |
| MOD-033 | no | sì | realizzata: `set-step finestra_giorni:` (1-90), date delle infrazioni (0801), livello più alto raggiunto | core/escalation_ladder_logic.py, escalation_repo.py; tests/test_catalogo_r2mod_scala.py |
| MOD-034 | in parte (durata solo per i timeout) | sì | in parte: durata per gradino di timeout c'è; mute a tempo e tempban nella scala NON fatti | escalation.py; tests/test_catalogo_r2mod_scala.py |
| MOD-035 | no | sì | realizzata: `enable azzera_dopo_scatto:` azzera conteggio e date, i casi restano | escalation.py; tests/test_catalogo_r2mod_scala.py |
| MOD-040 | in parte (`classifica-staff moderatore:` elenca gli ultimi casi) | sì | NON completata: mancano i conteggi per tipo e per periodo | tests/test_moderation_caso_note_warn.py::test_classifica_staff_e_casi_del_moderatore |
| MOD-051 | no | - | NON FATTA: serve `message_content` e un file allegato al caso; in parte coperta da `/mod-canali esporta-chat` | resta aperta |
| MOD-052 | sì (il passo «moderazione» di `/admin-bot setup` crea `#mod-log` riservato) | sì | segnata | tests/test_setup_wizard.py::test_il_canale_modlog_si_crea_riservato_e_si_collega |
| MOD-053 | no | - | NON FATTA (meglio dal pannello web) | resta aperta |
| MOD-060 | no | - | NON FATTA: tipo di uscita «avvisi sanzione» nel router | resta aperta |
| MOD-061 | sì (`/mod-sanzioni opzioni dm testo:` + bottone «Fai appello» nel DM) | sì | segnata | tests/test_moderation_appelli.py::test_dm_di_chi_ha_un_ban_manuale_riceve_il_bottone; tests/test_catalogo_r2mod_appelli.py |
| MOD-062 | sì (`/mod-ban appelli canale`; non passa dal router dei canali) | sì | segnata | tests/test_moderation_appelli.py::test_comandi_appelli_canale_ed_elenco |
| MOD-063 | no | sì | realizzata: `/mod-ban appelli timeout`; accettare toglie il timeout solo se chi decide sta sopra l'utente; «Moderare i membri» decide solo i timeout | ban_appeal.py; tests/test_catalogo_r2mod_appelli.py |
| MOD-091 | no | - | NON FATTA (blocco di più canali scelti) | resta aperta |
| MOD-092 | no | - | NON FATTA (gruppo di canali predefinito) | resta aperta |
| MOD-093 | sì (`/mod-canali blocco attiva`, stato salvato, 500 canali) | sì | realizzato il tempo: `minuti:` (al massimo 1440), si riapre dallo scheduler | core/lockdown_service.py; tests/test_catalogo_r2mod_blocco.py, tests/test_lockdown.py |
| MOD-094 | no | - | NON FATTA (blocco «cieco») | resta aperta |
| MOD-095 | no | - | NON FATTA (kick/ban di chi entra durante il blocco) | resta aperta |
| MOD-096 | no | - | NON FATTA (blocco dei permessi dei ruoli) | resta aperta |
| MOD-097 | in parte (solo `/admin-sicurezza panico stato`) | sì | realizzata: `/mod-canali blocco stato` | cogs/security/lockdown.py; tests/test_catalogo_r2mod_blocco.py |
| MOD-103 | no | - | NON FATTA (storico nomi, tabella con scadenza) | resta aperta |
| MOD-104 | no | - | NON FATTA (nickname e mute vocale ridati a chi rientra) | resta aperta |
| MOD-109 | in parte (`/mod-casi membri` con `entrato_dopo` e `account_piu_giovane_di`, senza ordinamento) | sì | segnata; l'ordinamento a 25 righe non c'è | tests/test_moderation_ricerca_m9.py::test_filtri_membri |
| MOD-111 | sì (`/utility permessi membro: canale:`, in `cogs/utility/schede.py`) | sì | test aggiunto sul membro | tests/test_catalogo_r2mod_mute.py::test_i_permessi_di_un_membro_in_un_canale_si_vedono_con_utility_permessi |

## 02-automod

Giro r2mod (issue #115, #116, #118). «Corretta» = fa ciò che dice il catalogo e rispetta SICUREZZA.md (gerarchia, permessi riletti, motivi entro 512, menzioni spente).

| codice | esiste | corretta | azione | file e test |
|---|---|---|---|---|
| AMD-030 | no | - | non fattibile ora, D104: serve una chiave API con quota (Google Safe Browsing) da scrivere in LIMITI.md | DECISIONI.md D104 |
| AMD-031 | no | - | NON FATTA (liste di siti per adulti e malware in `core/phishing_logic.py`) | resta aperta |
| AMD-057 | no | - | NON FATTA (blocco automatico per troppe menzioni) | resta aperta |
| AMD-071 | no | - | NON FATTA (modalità panico dell'AutoMod) | resta aperta |

## 04-verifica

Giro r2mod (issue #115, #116, #118). «Corretta» = fa ciò che dice il catalogo e rispetta SICUREZZA.md (gerarchia, permessi riletti, motivi entro 512, menzioni spente).

| codice | esiste | corretta | azione | file e test |
|---|---|---|---|---|
| VER-001 | sì (`captcha_tipo: immagine`, Pillow) | sì | segnata | tests/test_captcha_image.py::test_clic_con_immagine_manda_file_e_bottone_poi_modulo_poi_ruolo |
| VER-002 | no | - | NON FATTA (misura, colori, lunghezza) | resta aperta |
| VER-003 | in parte (la prova scade dopo 180 s) | sì | NON completata: manca il bottone «nuovo captcha» | core/captcha_image.py |
| VER-004 | in parte (3 tentativi per prova, poi blocco con motivo) | sì | segnata; l'azzeramento dello staff è `verify manuale` (verifica a mano) | tests/test_captcha_image.py::test_la_sfida_finisce_dopo_tre_errori |
| VER-005 | sì (modo «Pagina web» con link firmato di 15 minuti; senza captcha esterno) | sì | segnata | tests/test_alt_detection.py::test_pagina_verifica_e_doppio_segnalato |
| VER-006 | no | - | NON FATTA (testo scritto dal server sulla pagina) | resta aperta |
| VER-007 | in parte (`verify invia` a mano) | sì | NON completata: manca il DM automatico all'ingresso | tests/test_verify_r10.py::test_invia_rimanda_l_invito_al_membro |
| VER-018 | non verificato | - | NON FATTA | resta aperta |
| VER-021 | sì (impronta HMAC per server, mai l'IP in chiaro) | sì | segnata | tests/test_alt_detection.py::test_repo_trova_i_doppi_solo_nello_stesso_server |
| VER-022 | sì (avviso con elenco degli account collegati, menzioni spente) | sì | segnata | tests/test_alt_detection.py::test_avviso_allo_staff_senza_menzioni |
| VER-023 | no | - | NON FATTA (ruolo da avvisare) | resta aperta |
| VER-024 | sì come scelta (nessun ban automatico, solo avviso) | sì | segnata; il bottone «Banna» dell'alternativa NON c'è | tests/test_alt_detection.py::test_avviso_allo_staff_senza_menzioni |
| VER-025 | no | - | non fattibile, D104: le impronte sono diverse in ogni server per privacy (D19) | DECISIONI.md D104 |
| VER-026 | sì (strati ASN, Tor, elenchi, servizio; staff può far passare) | sì | segnata | tests/test_verify_vpn_flusso.py::test_vpn_bloccata_subito_con_avviso_e_nessun_dato_in_piu |
| VER-027 | no | - | non fattibile ora, D104: serve OAuth con `role_connections.write` e i metadati dell'applicazione | DECISIONI.md D104 |
| VER-028 | no | - | NON FATTA (pannello personalizzabile) | resta aperta |

## Voci passate da altri controlli

| codice | esiste | corretta | azione | file e test |
|---|---|---|---|---|
| UTL-204 | no | sì | realizzata: `/mod-canali esporta-chat` (1-1000 messaggi, file sotto 9,5 MB, allegati solo come scheda, permessi riletti, riga nel log) | core/moderation_esporta_chat.py, cogs/moderation/clear.py; tests/test_catalogo_r2mod_esporta_chat.py |
| UTL-205 | no | sì | realizzata: opzione `utente` di `/utility messaggio`, ognuno vede i suoi, chi gestisce i messaggi di tutti, sempre in privato | cogs/utility/snipe.py; tests/test_catalogo_r2mod_snipe_utente.py |
| CFG-024 | no | - | NON FATTA: i livelli mod/modban (`core/command_access.py`) danno il permesso per classe di comandi, non per singola azione | resta aperta |
