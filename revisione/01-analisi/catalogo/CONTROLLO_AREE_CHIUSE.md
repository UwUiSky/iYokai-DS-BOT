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
| UTL-226 | sì (`/admin-bot config pulisci`, 7 giorni, D111) | sì | nessuna | tests/test_config_orfani.py |
| UTL-227 | sì (`ruolo-richiesto`) | sì | nessuna | test_cfg012_serve_uno_dei_ruoli_richiesti_per_il_comando_e_il_suo_gruppo |
| UTL-228 | sì (`/admin-bot config reset anche_i_dati`, 30 giorni, D111) | sì | nessuna | tests/test_azzeramento_dati.py |

## 01-moderazione

Giro r2mod (issue #115, #116, #118). «Corretta» = fa ciò che dice il catalogo e rispetta SICUREZZA.md (gerarchia, permessi riletti, motivi entro 512, menzioni spente).

| codice | esiste | corretta | azione | file e test |
|---|---|---|---|---|
| MOD-008 | no | sì | realizzata: `appello: no` su ban, tempban e timeout; caso segnato (0800), niente bottone, appello rifiutato | cogs/moderation/actions.py, ban_appeal.py; tests/test_catalogo_r2mod_appelli.py |
| MOD-016 | no | sì | realizzata: `/mod-sanzioni quarantena` (anche a tempo, fino a 1 anno) e `libera`; usa il ruolo dell'anti-raid; i ruoli si salvano PRIMA (0804), il rilascio ridà solo quelli che il bot può ridare; gerarchia, conferma, permesso del bot e caso come ogni sanzione; azione `quarantena` concedibile a un ruolo (CFG-024) | core/moderation_quarantena.py, cogs/moderation/softban_mute.py; tests/test_catalogo_r2mod_quarantena.py |
| MOD-018 | no (il ruolo nasceva solo da solo) | sì | realizzata: `/mod-sanzioni opzioni muto ruolo:\|nome_nuovo:`; il ruolo deve stare sotto il bot e sotto chi comanda, non gestito, senza permessi pericolosi | cogs/moderation/opzioni.py; tests/test_catalogo_r2mod_mute.py |
| MOD-019 | no | sì | realizzata: `muto aggiorna:` rimette il blocco su fino a 500 canali, a gruppi di 8 con pausa | softban_mute.aggiorna_ruolo_muto; tests/test_catalogo_r2mod_mute.py |
| MOD-020 | sì (`add_reactions` già negato) | sì | test aggiunto | softban_mute.MUTE_OVERWRITE; tests/test_catalogo_r2mod_mute.py |
| MOD-032 | sì (`conta_warn_manuali`) | sì (gerarchia e permessi del moderatore, in massa mai kick/ban) | segnata | tests/test_escalation_warn_manuali.py::test_tre_warn_manuali_fanno_scattare_il_gradino |
| MOD-033 | no | sì | realizzata: `set-step finestra_giorni:` (1-90), date delle infrazioni (0801), livello più alto raggiunto | core/escalation_ladder_logic.py, escalation_repo.py; tests/test_catalogo_r2mod_scala.py |
| MOD-034 | in parte (durata solo per i timeout) | sì | completata: gradino `tempban` con durata (ban che finisce da solo, stesso scheduler di `/mod-ban tempban`; parte solo se chi ha dato il warn potrebbe bannare, mai dai warn in massa). Il mute a ruolo a tempo non c'è: il timeout è il mute a tempo | cogs/automod/escalation.py; tests/test_catalogo_r2mod_scala.py |
| MOD-035 | no | sì | realizzata: `enable azzera_dopo_scatto:` azzera conteggio e date, i casi restano | escalation.py; tests/test_catalogo_r2mod_scala.py |
| MOD-040 | in parte | sì | completata: `classifica-staff moderatore:` mostra i casi per tipo e negli ultimi 7, 30 e 90 giorni (i nascosti non contano) | core/repositories/moderation_repo.statistiche_moderatore; tests/test_catalogo_r2mod_stat_moderatore.py |
| MOD-051 | no | sì | realizzata: con `/mod-sanzioni opzioni memoria registro_chat: sì` (spento di base) warn, timeout, kick e ban salvano gli ultimi 100 messaggi del canale col caso (0806, 30 giorni nel registro dei dati, tolto col caso); si legge con `/mod-casi caso chat numero:` in privato; degli allegati solo nome pulito, tipo e peso (D74); un errore non ferma la sanzione. Dai comandi di massa e da tempban/softban non si salva | core/moderation_registro_chat.py, cogs/moderation/actions.py, case_system.py; tests/test_catalogo_r2mod_registro_chat.py |
| MOD-052 | sì (il passo «moderazione» di `/admin-bot setup` crea `#mod-log` riservato) | sì | segnata | tests/test_setup_wizard.py::test_il_canale_modlog_si_crea_riservato_e_si_collega |
| MOD-053 | no | sì | realizzata: `/mod-sanzioni opzioni aspetto tipo: colore: icona:` per warn, timeout, mute, kick, ban, tempban, softban, isolamento, quarantena; cambia solo il riquadro nel log di moderazione (il tipo si riconosce dal titolo; copia, l'originale non cambia); valori controllati prima di salvare, «nessuno» toglie la scelta. Il pannello web resta da fare (dev-web) | core/moderation_aspetto.py, cogs/moderation/_shared.post_to_mod_log; tests/test_catalogo_r2mod_aspetto.py |
| MOD-060 | no | sì | realizzata: `/mod-sanzioni opzioni avvisi canale:`; l'avviso va nel canale con la menzione della sola persona; senza permessi del bot o per un ban per ID resta il DM; `dm: no` spegne anche l'avviso | cogs/moderation/_shared._avviso_in_canale, cogs/moderation/opzioni.py; tests/test_catalogo_r2mod_avvisi.py |
| MOD-061 | sì (`/mod-sanzioni opzioni dm testo:` + bottone «Fai appello» nel DM) | sì | segnata | tests/test_moderation_appelli.py::test_dm_di_chi_ha_un_ban_manuale_riceve_il_bottone; tests/test_catalogo_r2mod_appelli.py |
| MOD-062 | sì (`/mod-ban appelli canale`; non passa dal router dei canali) | sì | segnata | tests/test_moderation_appelli.py::test_comandi_appelli_canale_ed_elenco |
| MOD-063 | no | sì | realizzata: `/mod-ban appelli timeout`; accettare toglie il timeout solo se chi decide sta sopra l'utente; «Moderare i membri» decide solo i timeout | ban_appeal.py; tests/test_catalogo_r2mod_appelli.py |
| MOD-091 | no | sì | realizzata: `/mod-canali blocco canali` con un menu fino a 25 canali; il server (verifica, inviti) resta com'è; si riapre con `blocco togli`; permesso riletto a ogni clic | cogs/security/lockdown.py, core/lockdown_service.py; tests/test_catalogo_r2mod_blocco_mirato.py |
| MOD-092 | no | sì | realizzata: «Salva come gruppo» nel menu (al massimo 25, 0803) e `blocco canali gruppo: sì` | core/repositories/lockdown_repo.py; tests/test_catalogo_r2mod_blocco_mirato.py |
| MOD-093 | sì (`/mod-canali blocco attiva`, stato salvato, 500 canali) | sì | realizzato il tempo: `minuti:` (al massimo 1440), si riapre dallo scheduler | core/lockdown_service.py; tests/test_catalogo_r2mod_blocco.py, tests/test_lockdown.py |
| MOD-094 | no | sì | realizzata: `blocco attiva nascondi:` toglie `view_channel` a @everyone, crea `#server-bloccato` in sola lettura e lo toglie allo sblocco (solo se l'ha creato il bot); senza il canale il blocco parte lo stesso | core/lockdown_service.py; tests/test_catalogo_r2mod_blocco_mirato.py |
| MOD-095 | no | sì | realizzata: `blocco attiva ingressi: espelli\|banna`; mai bot né protetti, serve il permesso vero a chi comanda e al bot, caso scritto, la scelta si rilegge dopo un riavvio e si spegne con lo sblocco | cogs/security/lockdown.py; tests/test_catalogo_r2mod_blocco_mirato.py |
| MOD-096 | no | sì | realizzata: `blocco attiva ruoli: sì` toglie i permessi critici ai ruoli sotto il bot (mai @everyone, gestiti, pari o sopra il bot), salva i bit tolti prima; lo sblocco rimette solo quelli, e se un ruolo non si riapre il blocco resta | core/lockdown_service.py; tests/test_catalogo_r2mod_blocco_mirato.py |
| MOD-097 | in parte (solo `/admin-sicurezza panico stato`) | sì | realizzata: `/mod-canali blocco stato` | cogs/security/lockdown.py; tests/test_catalogo_r2mod_blocco.py |
| MOD-103 | no | sì | realizzata: `/mod-casi nomi utente:` (soprannomi, nomi utente e nomi visualizzati, ultimi 30 per persona, scadenza 90 giorni nel registro dei dati, 0805); spento di base, si accende con `/mod-sanzioni opzioni memoria`; nomi senza menzioni né markdown | cogs/moderation/nickname.py, core/moderation_nomi.py; tests/test_catalogo_r2mod_nomi.py |
| MOD-104 | no | sì | realizzata: chi esce e rientra entro 30 giorni riprende il soprannome (solo se il bot può e il membro non sta sopra il bot) e il mute vocale alla prossima entrata in vocale, una volta sola; spento di base (`opzioni memoria`) | cogs/moderation/nickname.py; tests/test_catalogo_r2mod_nomi.py |
| MOD-109 | in parte (`/mod-casi membri` con `entrato_dopo` e `account_piu_giovane_di`, senza ordinamento) | sì | segnata; l'ordinamento a 25 righe non c'è | tests/test_moderation_ricerca_m9.py::test_filtri_membri |
| MOD-111 | sì (`/utility permessi membro: canale:`, in `cogs/utility/schede.py`) | sì | test aggiunto sul membro | tests/test_catalogo_r2mod_mute.py::test_i_permessi_di_un_membro_in_un_canale_si_vedono_con_utility_permessi |

## 02-automod

Giro r2mod (issue #115, #116, #118). «Corretta» = fa ciò che dice il catalogo e rispetta SICUREZZA.md (gerarchia, permessi riletti, motivi entro 512, menzioni spente).

| codice | esiste | corretta | azione | file e test |
|---|---|---|---|---|
| AMD-030 | no | - | non fattibile ora, D106: serve una chiave API con quota (Google Safe Browsing) da scrivere in LIMITI.md | DECISIONI.md D106 |
| AMD-031 | no | in parte | realizzata la funzione: `/admin-filtri phishing siti: cattura IP\|adulti\|malware\|tutti\|nessuno`, violazione «Siti pericolosi» con le sue azioni e regole, chiave `phishing_siti` in AutomodAdvancedConfig, whitelist dei domini che vince. Le liste: IP logger (17 domini) e adulti (13) di partenza; la lista dei MALWARE è VUOTA (data/siti_malware.txt): la riempie l'owner con la fonte che sceglie, senza voci quella categoria non blocca niente | core/phishing_logic.py, core/automod_advanced_logic.py, data/siti_*.txt; tests/test_catalogo_r2mod_siti.py |
| AMD-057 | no | sì | realizzata: `/admin-filtri emergenza menzioni_soglia: menzioni_secondi: menzioni_minuti:` blocca i canali (servizio del blocco totale, si riapre da solo) alla soglia; bot e amministratori non contano, un blocco ogni 10 minuti al massimo; accenderla serve «Gestire il server» | core/automod_emergenza.py, cogs/automod/automod.py; tests/test_catalogo_r2mod_emergenza.py |
| AMD-071 | no | sì | realizzata: `/admin-filtri emergenza panico: panico_utenti:` a N persone che violano una regola in un minuto il panico dura 10 minuti; in panico un account sospetto (giovane o senza avatar) che viola ancora va in timeout di 10 minuti, con caso; mai protetti, esenti o sopra il bot | core/automod_emergenza.py; tests/test_catalogo_r2mod_emergenza.py |

## 04-verifica

Giro r2mod (issue #115, #116, #118). «Corretta» = fa ciò che dice il catalogo e rispetta SICUREZZA.md (gerarchia, permessi riletti, motivi entro 512, menzioni spente).

| codice | esiste | corretta | azione | file e test |
|---|---|---|---|---|
| VER-001 | sì (`captcha_tipo: immagine`, Pillow) | sì | segnata | tests/test_captcha_image.py::test_clic_con_immagine_manda_file_e_bottone_poi_modulo_poi_ruolo |
| VER-002 | no | sì | realizzata: `verify opzioni captcha_lunghezza: captcha_misura: captcha_colore:` (4-8 lettere, piccola/media/grande, colore scuro abbastanza da leggersi) | core/captcha_image.py, cogs/security/verify.py; tests/test_catalogo_r2mod_verifica.py |
| VER-003 | in parte (la prova scade dopo 180 s) | sì | completata: bottone «Codice nuovo», i tentativi già usati restano usati, al massimo 3 rinnovi | core/captcha_image.py; tests/test_catalogo_r2mod_verifica.py |
| VER-004 | in parte (3 tentativi per prova, poi blocco con motivo) | sì | segnata; l'azzeramento dello staff è `verify manuale` (verifica a mano) | tests/test_captcha_image.py::test_la_sfida_finisce_dopo_tre_errori |
| VER-005 | sì (modo «Pagina web» con link firmato di 15 minuti; senza captcha esterno) | sì | segnata | tests/test_alt_detection.py::test_pagina_verifica_e_doppio_segnalato |
| VER-006 | no | sì | realizzata: `verify opzioni testo_pagina:` (1000 caratteri, 20 righe, senza HTML), mostrato sopra il bottone della pagina | core/alt_detection_logic.testo_pagina_pulito, pannello_web/templates/verifica.html; tests/test_catalogo_r2mod_verifica.py |
| VER-007 | in parte (`verify invia` a mano) | sì | completata: `verify tempi dm_ingresso:` un DM all'ingresso (chi aspetta l'età lo riceve dopo), DM chiusi senza errori | cogs/security/verify.py; tests/test_catalogo_r2mod_verifica.py |
| VER-018 | non verificato | sì | realizzata via CFG-024: l'azione `verifica` data a un ruolo apre solo `verify manuale` e `verify invia` | core/moderation_permessi_azioni.py; tests/test_catalogo_r2mod_permessi_azioni.py |
| VER-021 | sì (impronta HMAC per server, mai l'IP in chiaro) | sì | segnata | tests/test_alt_detection.py::test_repo_trova_i_doppi_solo_nello_stesso_server |
| VER-022 | sì (avviso con elenco degli account collegati, menzioni spente) | sì | segnata | tests/test_alt_detection.py::test_avviso_allo_staff_senza_menzioni |
| VER-023 | no | sì | realizzata: `verify opzioni ruolo_avviso_alt:` (serve «Menziona tutti», mai @everyone), ping solo di quel ruolo | cogs/security/alt_detection.py; tests/test_catalogo_r2mod_verifica.py |
| VER-024 | sì come scelta (nessun ban automatico, solo avviso) | sì | segnata; il bottone «Banna» dell'alternativa NON c'è | tests/test_alt_detection.py::test_avviso_allo_staff_senza_menzioni |
| VER-025 | no | - | non fattibile, D106: le impronte sono diverse in ogni server per privacy (D19) | DECISIONI.md D106 |
| VER-026 | sì (strati ASN, Tor, elenchi, servizio; staff può far passare) | sì | segnata | tests/test_verify_vpn_flusso.py::test_vpn_bloccata_subito_con_avviso_e_nessun_dato_in_piu |
| VER-027 | no | - | non fattibile ora, D106: serve OAuth con `role_connections.write` e i metadati dell'applicazione | DECISIONI.md D106 |
| VER-028 | no | sì | realizzata: `verify panel titolo: testo: colore: bottone: emoji:` | core/verify_logic.pannello_personalizzato; tests/test_catalogo_r2mod_verifica.py |

## Voci passate da altri controlli

| codice | esiste | corretta | azione | file e test |
|---|---|---|---|---|
| UTL-204 | no | sì | realizzata: `/mod-canali esporta-chat` (1-1000 messaggi, file sotto 9,5 MB, allegati solo come scheda, permessi riletti, riga nel log) | core/moderation_esporta_chat.py, cogs/moderation/clear.py; tests/test_catalogo_r2mod_esporta_chat.py |
| UTL-205 | no | sì | realizzata: opzione `utente` di `/utility messaggio`, ognuno vede i suoi, chi gestisce i messaggi di tutti, sempre in privato | cogs/utility/snipe.py; tests/test_catalogo_r2mod_snipe_utente.py |
| CFG-024 | no | sì | realizzata: tabella `moderation_ruoli_azioni` (0802), `/mod-sanzioni opzioni azioni`, controllo in `core/command_access.controlla`; un ruolo con solo «timeout» non banna | core/moderation_permessi_azioni.py, core/command_access.py; tests/test_catalogo_r2mod_permessi_azioni.py |
## 17-divertimento-e-immagini

Giro r5eco (issue #131, controllo). «Corretta» = fa ciò che dice il catalogo e rispetta SICUREZZA.md. Le 91 voci FUN che lo stato segnava come non trovate.

| codice | esiste | corretta | azione | file e test |
|---|---|---|---|---|
| FUN-013 | no | sì | non realizzata: D103 (tela persistente da tenere e disegnare) | nessun file |
| FUN-014 | no | sì | non realizzata: D103 (tela persistente da tenere e disegnare) | nessun file |
| FUN-017 | no | sì | non realizzata: D103 (collezione di oggetti da progettare con il negozio) | nessun file |
| FUN-019 | no | sì | non realizzata: D103 (il duello a tiri di /giochi sfide duello copre la sfida; il combattimento a turni con bottoni resta da progettare) | cogs/fun/sfide.py (duello con posta) |
| FUN-022 | sì (`/fun misura`) | sì (tema filtrato, stabile nel giorno) | nessuna | cogs/fun/coin_games.py; tests/test_fun_controllo_area17.py::test_fun_022_misura_a_tema_libero_e_stabile_nel_giorno |
| FUN-024 | sì (`/fun dice formula`) | sì (tetto 20 dadi, 1000 facce, modificatore 1000: più prudente dei 30 del catalogo) | nessuna | cogs/fun/entertainment.py; tests/test_fun_controllo_area17.py::test_fun_024_dadi_in_formato_da_gioco_di_ruolo_con_tetto |
| FUN-025 | sì (`/fun numero`) | sì (intervallo invertito rifiutato) | nessuna | cogs/fun/fun_extra.py; tests/test_fun_controllo_area17.py::test_fun_025_numero_in_un_intervallo |
| FUN-027 | in parte (c'era solo la frase) | sì dopo la correzione (un voto per persona, bot esclusi, 10 minuti) | realizzati i due bottoni con il conteggio: `PreferireView` | cogs/fun/fun_extra.py; tests/test_fun_controllo_area17_db.py::test_fun_027_preferiresti_conta_un_voto_per_persona_e_i_bot_non_votano |
| FUN-028 | sì (`/fun casuale`) | sì (elenco curato in italiano) | nessuna | tests/test_fun_controllo_area17.py::test_fun_028_029_036_contenuti_curati_e_fun_027_coppie |
| FUN-029 | sì (`/fun casuale`) | sì (elenco curato in italiano) | nessuna | tests/test_fun_controllo_area17.py::test_fun_028_029_036_contenuti_curati_e_fun_027_coppie |
| FUN-031 | sì (`/fun scherzo`) | no (non rispettava il blocco personale di FUN-137) | corretta: ora lo scherzo si ferma se il bersaglio ha bloccato l'autore (stesso controllo delle GIF), menzioni sempre spente | cogs/fun/fun_extra.py `scherzo`; tests/test_fun_controllo_area17_db.py::test_fun_031_032_gli_scherzi_rispettano_il_blocco_personale |
| FUN-032 | sì (`/fun scherzo`) | no (non rispettava il blocco personale di FUN-137) | corretta: ora lo scherzo si ferma se il bersaglio ha bloccato l'autore (stesso controllo delle GIF), menzioni sempre spente | cogs/fun/fun_extra.py `scherzo`; tests/test_fun_controllo_area17_db.py::test_fun_031_032_gli_scherzi_rispettano_il_blocco_personale |
| FUN-034 | sì (`/fun fact animale`) | sì | nessuna | cogs/fun/entertainment.py; tests/test_fun_controllo_area17_db.py::test_fun_034_curiosita_su_gatti_e_cani |
| FUN-036 | sì (`/fun casuale`) | sì (elenco curato in italiano) | nessuna | tests/test_fun_controllo_area17.py::test_fun_028_029_036_contenuti_curati_e_fun_027_coppie |
| FUN-037 | sì (`/fun scherzo tipo:Cercalo su Google`) | sì (solo un link costruito, testo codificato; blocco personale ora rispettato) | nessuna | tests/test_fun_controllo_area17.py::test_fun_031_032_037_scherzi_e_link_costruito |
| FUN-038 | sì (`/fun testo`, stile largo) | sì (risposta al massimo 2000 caratteri) | nessuna | tests/test_fun_controllo_area17.py::test_stili_di_testo_cambiano_il_testo_e_non_superano_2000 |
| FUN-039 | sì (`/fun testo`, stile corsivo) | sì (risposta al massimo 2000 caratteri) | nessuna | tests/test_fun_controllo_area17.py::test_stili_di_testo_cambiano_il_testo_e_non_superano_2000 |
| FUN-040 | sì (`/fun testo`, stile corsivo grassetto) | sì (risposta al massimo 2000 caratteri) | nessuna | tests/test_fun_controllo_area17.py::test_stili_di_testo_cambiano_il_testo_e_non_superano_2000 |
| FUN-041 | sì (`/fun testo`, stile gotico) | sì (risposta al massimo 2000 caratteri) | nessuna | tests/test_fun_controllo_area17.py::test_stili_di_testo_cambiano_il_testo_e_non_superano_2000 |
| FUN-042 | sì (`/fun testo`, stile gotico grassetto) | sì (risposta al massimo 2000 caratteri) | nessuna | tests/test_fun_controllo_area17.py::test_stili_di_testo_cambiano_il_testo_e_non_superano_2000 |
| FUN-043 | sì (`/fun testo`, stile doppio tratto) | sì (risposta al massimo 2000 caratteri) | nessuna | tests/test_fun_controllo_area17.py::test_stili_di_testo_cambiano_il_testo_e_non_superano_2000 |
| FUN-044 | sì (`/fun testo`, stile maiuscoletto) | sì (risposta al massimo 2000 caratteri) | nessuna | tests/test_fun_controllo_area17.py::test_stili_di_testo_cambiano_il_testo_e_non_superano_2000 |
| FUN-045 | sì (`/fun testo`, stile emoji delle lettere) | sì (risposta al massimo 2000 caratteri) | nessuna | tests/test_fun_controllo_area17.py::test_stili_di_testo_cambiano_il_testo_e_non_superano_2000 |
| FUN-046 | sì (`/fun testo`, stile applauso) | sì (risposta al massimo 2000 caratteri) | nessuna | tests/test_fun_controllo_area17.py::test_stili_di_testo_cambiano_il_testo_e_non_superano_2000 |
| FUN-047 | sì (`/fun testo`, stile separatore a scelta) | sì (risposta al massimo 2000 caratteri) | nessuna | tests/test_fun_controllo_area17.py::test_stili_di_testo_cambiano_il_testo_e_non_superano_2000 |
| FUN-048 | sì (`/fun testo`, stile owo) | sì (risposta al massimo 2000 caratteri) | nessuna | tests/test_fun_controllo_area17.py::test_stili_di_testo_cambiano_il_testo_e_non_superano_2000 |
| FUN-059 | sì (`/immagini effetto`) | sì (file rovinato: nessun errore; la GIF «triggered» pesa meno di 1 MB) | nessuna | core/image_effects_logic.py; tests/test_fun_controllo_area17.py::test_fun_059_060_061_effetti_sull_avatar |
| FUN-060 | sì (`/immagini effetto`) | sì (file rovinato: nessun errore; la GIF «triggered» pesa meno di 1 MB) | nessuna | core/image_effects_logic.py; tests/test_fun_controllo_area17.py::test_fun_059_060_061_effetti_sull_avatar |
| FUN-061 | sì (`/immagini effetto`) | sì (file rovinato: nessun errore; la GIF «triggered» pesa meno di 1 MB) | nessuna | core/image_effects_logic.py; tests/test_fun_controllo_area17.py::test_fun_059_060_061_effetti_sull_avatar |
| FUN-067 | sì (`/web scheda`) | sì (servizi con cache, spenti se manca la chiave; contenuto per adulti solo nei canali con limite d'età) | nessuna | cogs/fun/schede_giochi.py; tests/test_fun_controllo_area17.py::test_fun_067_068_069_070_073_la_scheda_sul_web_ha_i_servizi_del_catalogo |
| FUN-068 | sì (`/web scheda`) | sì (servizi con cache, spenti se manca la chiave; contenuto per adulti solo nei canali con limite d'età) | nessuna | cogs/fun/schede_giochi.py; tests/test_fun_controllo_area17.py::test_fun_067_068_069_070_073_la_scheda_sul_web_ha_i_servizi_del_catalogo |
| FUN-069 | sì (tabella dei tipi in `debolezze`) | sì | nessuna | core/schede_giochi_logic.py; tests/test_fun_controllo_area17.py::test_fun_067_068_069_070_073_la_scheda_sul_web_ha_i_servizi_del_catalogo |
| FUN-070 | sì (`/web scheda`) | sì (servizi con cache, spenti se manca la chiave; contenuto per adulti solo nei canali con limite d'età) | nessuna | cogs/fun/schede_giochi.py; tests/test_fun_controllo_area17.py::test_fun_067_068_069_070_073_la_scheda_sul_web_ha_i_servizi_del_catalogo |
| FUN-073 | sì (`/web scheda`) | sì (servizi con cache, spenti se manca la chiave; contenuto per adulti solo nei canali con limite d'età) | nessuna | cogs/fun/schede_giochi.py; tests/test_fun_controllo_area17.py::test_fun_067_068_069_070_073_la_scheda_sul_web_ha_i_servizi_del_catalogo |
| FUN-074 | sì (`/music suono`) | sì (solo suoni della soundboard di Discord, senza file nostri) | nessuna | cogs/fun/soundboard.py; tests/test_fun_controllo_area17.py::test_fun_074_075_077_suoni_del_server_con_completamento |
| FUN-075 | in parte (i suoni del server sono quelli della soundboard di Discord, non file caricati da noi) | sì | nessuna: caricare file propri nel bot è fuori scelta (nessun file di terzi sul nostro disco; D70) | cogs/fun/soundboard.py; tests/test_fun_controllo_area17.py::test_fun_074_075_077_suoni_del_server_con_completamento |
| FUN-077 | sì (completamento a 25 voci) | sì | nessuna | cogs/fun/soundboard.py; tests/test_fun_controllo_area17.py::test_fun_074_075_077_suoni_del_server_con_completamento |
| FUN-078 | no | sì | non realizzata: D103 (un suono di soundboard dura pochi secondi e Discord non permette di fermarlo) | nessun file |
| FUN-082 | sì | sì (categoria sicura, frase it/en, menzioni spente) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-083 | sì | sì (categoria sicura, frase it/en, menzioni spente) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-084 | sì | sì (categoria sicura, frase it/en, menzioni spente) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-085 | sì | sì (categoria sicura, frase it/en, menzioni spente) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-086 | sì | sì (categoria sicura, frase it/en, menzioni spente) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-087 | sì | sì (categoria sicura, frase it/en, menzioni spente) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-088 | sì | sì (categoria sicura, frase it/en, menzioni spente) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-089 | sì | sì (categoria sicura, frase it/en, menzioni spente) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-090 | sì | sì (categoria sicura, frase it/en, menzioni spente) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-091 | sì | sì (categoria sicura, frase it/en, menzioni spente) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-092 | sì | sì (categoria sicura, frase it/en, menzioni spente) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-093 | sì | sì (categoria sicura, frase it/en, menzioni spente) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-094 | sì | sì (categoria sicura, frase it/en, menzioni spente) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-095 | sì | sì (categoria sicura, frase it/en, menzioni spente) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-096 | sì | sì (categoria sicura, frase it/en, menzioni spente) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-097 | sì | sì (categoria sicura, frase it/en, menzioni spente) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-098 | sì | sì (categoria sicura, frase it/en, menzioni spente) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-099 | sì | sì (categoria sicura, frase it/en, menzioni spente) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-100 | sì | sì (categoria sicura, frase it/en, menzioni spente) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-101 | in parte (frase e nome nelle due lingue, nessuna GIF: manca una raccolta con licenza chiara) | sì (risponde con la sola frase) | nessuna: voce nel cricchetto SENZA_FONTE (D103), si toglie quando arriva una fonte | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-102 | sì | sì (categoria sicura, frase it/en, menzioni spente) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-103 | sì | sì (categoria sicura, frase it/en, menzioni spente) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-104 | in parte (frase e nome nelle due lingue, nessuna GIF: manca una raccolta con licenza chiara) | sì (risponde con la sola frase) | nessuna: voce nel cricchetto SENZA_FONTE (D103), si toglie quando arriva una fonte | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-105 | in parte (frase e nome nelle due lingue, nessuna GIF: manca una raccolta con licenza chiara) | sì (risponde con la sola frase) | nessuna: voce nel cricchetto SENZA_FONTE (D103), si toglie quando arriva una fonte | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-106 | sì | sì (categoria sicura, frase it/en, menzioni spente) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-107 | sì | sì (categoria sicura, frase it/en, menzioni spente) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-108 | sì | sì (categoria sicura, frase it/en, menzioni spente) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-109 | sì | sì (categoria sicura, frase it/en, menzioni spente) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-111 | sì | sì (categoria sicura, frase it/en, menzioni spente; blocco personale rispettato (`esito_azione`)) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-112 | sì | sì (categoria sicura, frase it/en, menzioni spente; blocco personale rispettato (`esito_azione`)) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-113 | sì | sì (categoria sicura, frase it/en, menzioni spente; blocco personale rispettato (`esito_azione`)) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-114 | sì | sì (categoria sicura, frase it/en, menzioni spente; blocco personale rispettato (`esito_azione`)) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-115 | in parte (frase e nome nelle due lingue, nessuna GIF: manca una raccolta con licenza chiara) | sì (risponde con la sola frase) | nessuna: voce nel cricchetto SENZA_FONTE (D103), si toglie quando arriva una fonte | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-116 | sì | sì (categoria sicura, frase it/en, menzioni spente; blocco personale rispettato (`esito_azione`)) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-117 | sì | sì (categoria sicura, frase it/en, menzioni spente; blocco personale rispettato (`esito_azione`)) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-118 | sì | sì (categoria sicura, frase it/en, menzioni spente; blocco personale rispettato (`esito_azione`)) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-119 | sì | sì (categoria sicura, frase it/en, menzioni spente; blocco personale rispettato (`esito_azione`)) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-120 | sì | sì (categoria sicura, frase it/en, menzioni spente; blocco personale rispettato (`esito_azione`)) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-121 | sì | sì (categoria sicura, frase it/en, menzioni spente; blocco personale rispettato (`esito_azione`)) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-122 | sì | sì (categoria sicura, frase it/en, menzioni spente; blocco personale rispettato (`esito_azione`)) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-123 | sì | sì (categoria sicura, frase it/en, menzioni spente; blocco personale rispettato (`esito_azione`)) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-124 | sì | sì (categoria sicura, frase it/en, menzioni spente; blocco personale rispettato (`esito_azione`)) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-125 | sì | sì (categoria sicura, frase it/en, menzioni spente; blocco personale rispettato (`esito_azione`)) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-126 | sì | sì (categoria sicura, frase it/en, menzioni spente; blocco personale rispettato (`esito_azione`)) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-127 | in parte (frase e nome nelle due lingue, nessuna GIF: manca una raccolta con licenza chiara) | sì (risponde con la sola frase) | nessuna: voce nel cricchetto SENZA_FONTE (D103), si toglie quando arriva una fonte | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-128 | in parte (frase e nome nelle due lingue, nessuna GIF: manca una raccolta con licenza chiara) | sì (risponde con la sola frase) | nessuna: voce nel cricchetto SENZA_FONTE (D103), si toglie quando arriva una fonte | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-129 | sì | sì (categoria sicura, frase it/en, menzioni spente; blocco personale rispettato (`esito_azione`)) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-130 | sì | sì (categoria sicura, frase it/en, menzioni spente; blocco personale rispettato (`esito_azione`)) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-131 | sì | sì (categoria sicura, frase it/en, menzioni spente; blocco personale rispettato (`esito_azione`)) | nessuna | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-132 | in parte (frase e nome nelle due lingue, nessuna GIF: manca una raccolta con licenza chiara) | sì (risponde con la sola frase) | nessuna: voce nel cricchetto SENZA_FONTE (D103), si toglie quando arriva una fonte | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-133 | in parte (frase e nome nelle due lingue, nessuna GIF: manca una raccolta con licenza chiara) | sì (risponde con la sola frase) | nessuna: voce nel cricchetto SENZA_FONTE (D103), si toglie quando arriva una fonte | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-134 | in parte (frase e nome nelle due lingue, nessuna GIF: manca una raccolta con licenza chiara) | sì (risponde con la sola frase) | nessuna: voce nel cricchetto SENZA_FONTE (D103), si toglie quando arriva una fonte | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |
| FUN-135 | in parte (frase e nome nelle due lingue, nessuna GIF: manca una raccolta con licenza chiara) | sì (risponde con la sola frase) | nessuna: voce nel cricchetto SENZA_FONTE (D103), si toglie quando arriva una fonte | cogs/fun/gif.py; data/gif_catalogo.json; tests/test_fun_controllo_area17.py::test_ogni_voce_gif_esiste_con_frase_nelle_due_lingue_e_una_fonte |

## 06-ticket-e-modmail

Giro r2tkt (issue #120). «Corretta» = fa ciò che dice il catalogo e rispetta SICUREZZA.md. Difetto trovato e corretto in voci esistenti: `AllowedMentions(users=[...])` lasciava `everyone` e `roles` accesi (sollecito con testo che può venire dall'AI, regole di inattività, benvenuto, richiesta di chiusura); test in tests/test_ticket_standard.py e tests/test_ticket_catalogo_r2tkt_b.py. Un'eccezione nel log di chiusura poteva rompere la chiusura: ora è isolata.

| codice | esiste | corretta | azione | file e test |
|---|---|---|---|---|
| TKT-001 | sì | sì | nessuna (codice nel test) | cogs/tickets/tickets.py `vista_pannelli`, `pannello_pubblica`; tests/test_ticket_form.py::test_pubblica_due_pannelli_in_un_solo_messaggio |
| TKT-002 | no | - | realizzata | `pubblica per_riga`, `form.righe_di_bottoni`; tests/test_ticket_catalogo_r2tkt.py::test_tkt_002_* |
| TKT-003 | in parte (titolo e testo) | no: niente colore, miniatura, immagine | realizzata | `pubblica` con colore, miniatura, immagine o embed salvato (controllo `embed_builder.valida`); tests/test_ticket_catalogo_r2tkt.py::test_tkt_003_* |
| TKT-004 | in parte (testo, emoji) | no: niente colore | realizzata | `pannelli aspetto`, migrazione 0771; tests/test_ticket_catalogo_r2tkt.py::test_tkt_004_* |
| TKT-005 | in parte (nome, emoji) | no: niente descrizione né segnaposto | realizzata | descrizione di motivi e categorie, segnaposto del menu; tests/test_ticket_catalogo_r2tkt.py::test_tkt_005_* |
| TKT-010 | sì | sì | nessuna (codice nel test) | tests/test_ticket_form.py::test_la_sesta_domanda_e_rifiutata_e_le_posizioni_scorrono, test_invio_del_modulo_crea_il_ticket_con_le_risposte |
| TKT-011 | in parte (obbligatoria, riga, segnaposto) | no: niente minimo e massimo | realizzata | colonne `min_length`/`max_length` (0771), `modulo-aggiungi`; tests/test_ticket_catalogo_r2tkt.py::test_tkt_011_* |
| TKT-012 | no | - | realizzata (menu nelle finestre verificati in discord.py 2.7.1) | `_componente_domanda`, `modulo-aggiungi tipo`; tests/test_ticket_catalogo_r2tkt.py::test_tkt_012_* |
| TKT-013 | sì | sì | nessuna (codice nel test) | tests/test_ticket_catalogo.py::test_il_benvenuto_con_cinque_risposte_lunghe_resta_sotto_6000_e_il_ticket_nasce |
| TKT-014 | no | - | realizzata come copia, D101 | `modulo-copia`; tests/test_ticket_catalogo_r2tkt.py::test_tkt_014_* |
| TKT-015 | sì (limite del server, vincolo nel database) | sì; il tetto di pannello è TKT-017 | nessuna (codice nel test) | tests/test_tickets_correzioni.py::test_il_limite_regge_con_aperture_in_parallelo |
| TKT-016 | sì | sì | nessuna (codice nel test) | tests/test_tickets_correzioni.py::test_con_limite_due_il_cog_lascia_aprire_il_secondo_ticket |
| TKT-036 | in parte (solo {utente}) | no: segnaposto e embed salvato mancavano | realizzata | `form.testo_benvenuto` (un'unica passata, elenco chiuso, nomi puliti), `embed_apertura`; tests/test_ticket_catalogo_r2tkt.py::test_tkt_036_* |
| TKT-049 | sì | sì | nessuna (codice nel test) | tests/test_ticket_catalogo.py::test_passa_solo_a_un_membro_dello_staff |
| TKT-059 | sì | sì | nessuna (codice nel test) | tests/test_ticket_autoclose.py::test_ticket_fermo_da_piu_di_n_minuti_si_chiude_e_il_canale_va_allo_scheduler |
| TKT-060 | sì (regola «utente»: senza messaggi vale l'apertura) | sì | nessuna (codice nel test) | tests/test_ticket_r18.py::test_regola_utente_conta_dall_ultimo_messaggio_dell_utente |
| TKT-061 | sì | sì | nessuna (codice nel test) | tests/test_ticket_autoclose.py::test_utente_che_esce_dal_server_chiude_il_suo_ticket |
| TKT-062 | no | - | realizzata | `/ticket tieni-aperto`, colonna `tieni_aperto` (0772); tests/test_ticket_catalogo_r2tkt_b.py::test_tkt_062_* |
| TKT-065 | sì | sì | nessuna (codice nel test) | tests/test_ticket_form.py::test_il_clic_sul_voto_registra_le_stelle_una_volta_sola |
| TKT-066 | no | - | realizzata | `voto questionario`, `ModuloQuestionario`, tabella `ticket_questionario_risposte` (0772); tests/test_ticket_catalogo_r2tkt_b.py::test_tkt_066_* |
| TKT-069 | sì | sì | nessuna (codice nel test) | tests/test_ticket_catalogo.py::test_transcript_solo_staff_e_il_ticket_resta_aperto |
| TKT-072 | no | - | non fattibile D101 | il bot non salva il testo dei messaggi; è del pannello web (NF-20) |
| TKT-076 | in parte (solo transcript) | no: nessuna azione registrata | realizzata | `registra_azione`, `/admin-ticket log`, tipo «ticket» del router; tests/test_ticket_catalogo_r2tkt_b.py::test_tkt_076_* |
| TKT-077 | in parte (3 numeri) | no: mancavano i numeri avanzati | realizzata, con una variante (D101) | `stats dettagli`, `ticket_repo.get_statistiche_avanzate`; tests/test_ticket_catalogo_r2tkt_b.py::test_tkt_077_* |
| TKT-078 | in parte (articoli solo nel ModMail) | no: nei ticket non si potevano usare | realizzata | cogs/tickets/risposte.py `/ticket pronta`; tests/test_ticket_catalogo_r2tkt_b.py::test_tkt_078_* |
| TKT-080 | no | - | realizzata (4 modelli, it ed en) | core/ticket_modelli_logic.py, `pannelli modello`; tests/test_ticket_catalogo_r2tkt_c.py::test_tkt_080_* |
| TKT-081 | sì | sì | nessuna (codice nel test) | tests/test_modmail.py::test_il_dm_apre_un_canale_privato_per_lo_staff_e_inoltra_il_messaggio |
| TKT-082 | in parte (anonimo solo per risposta) | sì; la chiusura non mostra mai il nome | aggiornata (anonimo predefinito del server) | `modmail opzioni`, 0770; tests/test_modmail.py::test_senza_scelta_la_risposta_segue_il_predefinito_del_server |
| TKT-083 | no (solo con il comando) | - | realizzata | `inoltra_tutto`, `//` = nota interna; tests/test_modmail.py::test_inoltra_tutto_manda_il_testo_dello_staff_e_rispetta_le_note_interne |
| TKT-084 | in parte (conferma sempre accesa) | sì | aggiornata (conferma disattivabile) | tests/test_modmail.py::test_senza_conferma_il_primo_dm_apre_subito_il_canale |
| TKT-085 | no | - | non fattibile D101 | scrittura dal web a nome dello staff: pannello web |
| TKT-086 | no | - | realizzata (spento di base, D101) | cogs/ai/ticket_ai.py `riassunto_alla_chiusura`, 0773; tests/test_ticket_catalogo_r2tkt_c.py::test_tkt_086_* |
| TKT-087 | sì (`/ticket assistente`, bozza per lo staff) | sì: ephemeral, mai inviata | nessuna (test aggiunto) | cogs/ai/ticket_ai.py; tests/test_ticket_catalogo_r2tkt_b.py::test_tkt_087_* |

## 07-backup-e-restore

Giro r2bkp (issue #121). «Corretta» = fa ciò che dice il catalogo e rispetta SICUREZZA.md. Controlli in più: permessi pericolosi, gerarchia dei ruoli, file validati prima di leggerli, webhook senza menzioni (D74 per gli allegati), token mai nei log.

| codice | esiste | corretta | azione | file e test |
|---|---|---|---|---|
| BKP-001 | sì | sì (canali `___hidden___` e ruoli gestiti saltati; 10 copie; file entro 10 MiB) | nessuna (codice nel test) | cogs/utility/backup.py `salva`, core/backup_struttura_logic.py `leggi_struttura`, core/backup_orchestrator.py; tests/test_backup_struttura.py::test_lettura_salta_canali_offuscati_ruoli_gestiti_e_mappa_i_permessi_per_nome, tests/test_backup_queue_worker.py::test_tick_copia_sul_server_del_creator_e_notifica |
| BKP-002 | no | sì | realizzata: `salva thread:Sì` (thread pubblici attivi e archiviati, primo messaggio dei post), parte «thread» nel caricamento senza doppioni, `allowed_mentions` spento; thread privati mai letti | core/backup_struttura_logic.py `leggi_thread`, `Caricatore._thread`; tests/test_backup_thread.py |
| BKP-003 | sì | no: un ruolo nuovo con admin o gestione nasceva anche se caricava un non-owner | corretta: senza permessi pericolosi se non carica l'owner; ruolo esistente pericoloso non dato ai membri da chi non è l'owner | Caricatore `_ruoli`, `_membri`; tests/test_backup_struttura.py::test_ruolo_nuovo_con_permessi_pericolosi_nasce_senza_se_non_carica_l_owner, test_ruolo_esistente_pericoloso_non_si_da_ai_membri_da_chi_non_e_owner, test_caricamento_riusa_per_nome_e_adatta_il_bitrate |
| BKP-004 | sì (menu delle parti; non cancella mai) | sì | nessuna; «cancellare ciò che c'è già» non offerto di proposito (D108) | ScegliPartiView; tests/test_backup_struttura_cog.py::test_menu_delle_parti_e_caricamento_con_riepilogo_nel_canale, test_backup_struttura.py::test_parti_presenti_e_passi |
| BKP-005 | sì | sì (più nuovi per primi, automatiche segnate, al massimo 10 copie = una pagina) | nessuna; test di ordine aggiunto | backup_struttura_repo `lista_strutture`; tests/test_backup_automatico.py::test_la_lista_ha_i_piu_nuovi_per_primi |
| BKP-006 | no | sì | realizzata: `/admin-backup lista copia:N` (conteggi, data, tipo) senza caricare | cogs/utility/backup.py `_info_copia`, `struttura.riassunto`; tests/test_backup_struttura_cog.py::test_info_mostra_i_conteggi_senza_caricare |
| BKP-007 | in parte (una copia, senza conferma) | no: nessuna conferma | corretta e completata: bottone di conferma solo per chi ha chiesto, opzione `tutte` | `ConfermaEliminaView`; tests/test_backup_struttura_cog.py::test_elimina_chiede_conferma_e_tutte_toglie_ogni_copia |
| BKP-008 | no | sì | realizzata: `/founder backup automatico ore:4-168 copie:1-8`, la più vecchia automatica si sovrascrive, le copie a mano mai toccate (0810) | core/backup_automatico_logic.py, core/repositories/backup_automatico_repo.py, backup_queue_worker `tick`; tests/test_backup_automatico.py |
| BKP-011 | sì (0-100 messaggi per canale; ricarica solo in canali vuoti) | sì | nessuna | `salva messaggi:`; tests/test_backup_struttura.py::test_messaggi_ricaricati_solo_nei_canali_vuoti_con_lo_stesso_nome, tests/test_backup_messages_logic.py::test_ultimi_n_messaggi_e_tetto_predefinito |
| BKP-012 | sì | sì (un invio alla volta atteso, `allowed_mentions` spenti, nome senza discord/clyde, allegati D74 ricodificati) | nessuna | core/backup_messages_logic.py, core/backup_mirror_dispatch.py; tests/test_backup_messages_logic.py::test_invio_con_autore_senza_menzioni_e_con_allegati, tests/test_backup_mirror_dispatch.py |
| BKP-017 | sì | sì (codice 24 ore, legato a chi lo chiede, usato una volta) | nessuna | core/backup_link_logic.py; tests/test_backup_collegamento.py::test_il_codice_ha_la_forma_attesa_e_non_si_ripete, test_codice_giusto_collega_e_mette_in_coda_la_copia |
| BKP-020 | in parte (solo codice nostro) | sì | completata: nome di un modello pronto, codice nostro o link `discord.new` / `discord.com/template` (solo il codice va a Discord) | core/backup_modelli_logic.py, `modello usa`; tests/test_backup_modelli.py, tests/test_backup_struttura_cog.py::test_modello_di_discord_da_link_e_codice_sbagliato. Da provare live: lettura di un vero modello |
| BKP-021 | no | sì | realizzata: `modello elenco` e `modello scheda` | `BackupCog.modello`; tests/test_backup_struttura_cog.py::test_modello_pronto_elenco_e_scheda_senza_dati_personali |
| BKP-022 | in parte | sì per ciò che c'è | completata: tre modelli pronti nel bot; raccolta pubblica con ricerca e voti nel pannello web: D108 | core/backup_modelli_logic.py `MODELLI_PRONTI`; tests/test_backup_modelli.py::test_i_modelli_pronti_sono_validi_e_senza_permessi_pericolosi |
| BKP-023 | in parte (codice condivisibile, nessuna revisione) | sì per ciò che c'è | non fattibile nel bot: revisione prima della pubblicazione nel pannello web (D108) | tests/test_backup_struttura_cog.py::test_modello_si_pubblica_e_si_usa_senza_dati_personali |
| BKP-028 | in parte (solo mirror main → backup) | sì | realizzata: `/founder backup sincronia-canali` (una o due direzioni, solo owner di entrambi, webhook per canale, coda ordinata, bot e webhook mai copiati: niente cicli, 0811) | core/repositories/backup_sincronia_canali_repo.py, cogs/utility/backup_mirror.py; tests/test_backup_sincronia_canali.py |
| BKP-029 | sì | sì (senza eco, stesso proprietario) | nessuna (codice nel test) | `BackupCog._ban_sincronizzato`; tests/test_server_sync_logic.py::test_ban_copiato_una_volta_senza_eco |
| BKP-030 | sì | sì (ruoli per nome, mai con più permessi dell'originale) | nessuna | core/server_sync_logic.py; tests/test_server_sync_logic.py::test_ruoli_per_nome_e_niente_chiamate_se_gia_uguale, test_ruolo_omonimo_con_piu_permessi_non_si_da |
| BKP-031 | sì | sì | test aggiunto per l'elenco e «disattiva» dal comando | `sincronia`; tests/test_server_sync_logic.py::test_elenco_e_disattiva_dal_comando, test_repository_coppia_unica_e_tetto |
| BKP-038 | sì | sì (token cifrati con dato associato, rinnovo, 429, pause tra i DM, link di 7 giorni legato al destinatario, DM solo a chi ha acconsentito) | test aggiunto: nessun token nei log se il rinnovo o il join falliscono | core/restore_orchestrator.py, cogs/utility/restore.py; tests/test_restore_f3.py::test_nessun_token_nei_log_quando_il_rinnovo_fallisce, test_un_429_attende_il_retry_after_e_riprova, tests/test_restore_consenso.py::test_senza_consenso_nessun_dm |
| BKP-039 | no | n/a | non fattibile nel codice (dominio, certificato e proxy per server): D108 | — |
| BKP-040 | no | n/a | alternativa: il restore non raccoglie IP né paese (D108); regole per VPN e paese restano alla verifica | tests/test_restore_oauth_repo.py::test_il_ripristino_non_raccoglie_indirizzi_ip |
| BKP-041 | no | n/a | non fatta: manca la sezione backup nel pannello web (dev-web), D108 | — |

## 18-ai

Giro r2bkp (issue #132). Il codice AI passa sempre dalla porta unica `core/ai_servizio.py` (consenso, quote, filtri, tetto di spesa).

| codice | esiste | corretta | azione | file e test |
|---|---|---|---|---|
| AI-001 | no (solo `chiedi` sui comandi e la risposta alla menzione) | sì | realizzata: `/assistente scrivi richiesta:` (3-500 caratteri, risposta pubblica o privata, menzioni neutre, filtri e quote della porta unica) | cogs/ai/summaries.py `scrivi`, core/ai_testi_logic.py `ISTRUZIONI["scrivi"]`; tests/test_ai_cogs.py::test_scrivi_testo_a_richiesta_senza_menzioni_e_solo_con_consenso |
| AI-003 | in parte | sì per ciò che c'è | diritto del server (modulo premium `ai` + prova di 7 giorni) e uso personale con quota propria già presenti; abbonamento personale a pagamento non fattibile (D108) | core/ai_servizio.py; tests/test_ai_servizio.py::test_modulo_premium_non_sbloccato_ferma_anche_le_funzioni_automatiche, test_dm_senza_server_solo_gratuiti |
| AI-004 | sì (`/assistente immagina`) | no: l'immagine del servizio non si ricontrollava dopo la generazione | corretta: controllo e ricodifica in PNG dai soli pixel, tetto 9,5 MiB (D74), errore se non è un'immagine | core/ai_immagini_logic.py `ripulisci`, cogs/ai/images.py `genera`; tests/test_ai_cogs.py::test_immagina_con_bottoni_e_ingrandisci, test_immagine_generata_non_valida_non_si_manda |
| AI-010 | sì (`/admin-ai lore`) | sì (tetto 1000 caratteri come AI-R-051, non 2000: D108; dati personali tolti dalle istruzioni) | nessuna (codice nel test) | cogs/ai/config.py `lore`, core/ai_impostazioni.py `imposta_lore`; tests/test_ai_cogs.py::test_limiti_privacy_lore_vietate, tests/test_ai_servizio.py::test_lore_e_dati_personali |
| AI-017 | in parte (server e canale; menzione, bandiere, moderazione) | sì | completata: `/admin-ai interruttore` per scrivi, chiedi, traduci, riassumi, spiega, stile, immagina, ricerca, ticket, giochi (0812); tutto resta spento finché non si accende l'AI | core/ai_servizio.py `controlla_accesso`, core/ai_impostazioni.py `imposta_interruttore`; tests/test_ai_cogs.py::test_interruttore_spegne_una_funzione_per_volta, tests/test_ai_servizio.py::test_spenta_finche_non_ce_il_consenso |

