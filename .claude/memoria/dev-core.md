# Memoria di dev-core

## Aggiornata
14/10/2026 · ramo `feat/r5-cor` (base main) · giro r5: per FILE

## In corso
- Giro r5 chiuso (7 gruppi): lingue, traduttore, ricerca, #122 piccole, NF-22, NF-38, #141. Resta il rapporto all'orchestratore.
- Prossimo passo: far rispondere ai comandi il bot del marchio (NF-38, serve un disegno: oggi il client del marchio non ha comandi);
  poi CFG-011/013/014/016/024/025/026/030/033/039/043/044 di #122; 14.1 nei cog altrui; #140 (serve #95 + token GitHub).

## Fatto
- Giri precedenti (R1-bis, smoke, F7 quadro, NF-04 privacy/GDPR 0034-0036/0050, #148 permessi 0039, #145 premium_cache, M 13.1-13.3,
  M 14.1-14.12, 14.15): vedi `git log` e il registro delle risolte. Giro 12/10 bis e 12/10: revisioni su privacy, scheduler, OAuth.
- r5 g1-3 (6d0e6f6, 4379e18, 5add20b): `locales/it|en.json`, `core/i18n.py`, `user_language` 0130, `/utility lingua`;
  `core/command_translator.py` + `locales/comandi.en.json`; ricerca bilingue + `filtra_per_moduli`.
- r5 g4-7 (0ecc8ff, 8a38d4e, c5033ef, 0c08903): `core/command_policy.py` + `/utility politica`; `config_history` filtri/CSV;
  `/admin config pulizia|sincronizza|nickname-bot`, `/utility info`; NF-22 `premium_entitlements` 0131 + `/admin premium stato`;
  codici 0132 (`/owner premium grant` senza server crea il codice, `/admin premium riscatta`); NF-38 0133 `whitelabel_bots` +
  `/admin premium marchio`; #141 `core/hot_patch.py` 0134 (`/owner cog reload commit|file|registro`, `ENABLE_HOT_PATCH`).

## Cose imparate
- Discord conta per il limite 8000 solo la traduzione PIU LUNGA per campo (base compresa). Base del codice resta italiano (scarto da D1).
- discord.py mette locale_str automatico su nomi/descrizioni: il traduttore riceve `context.data` (nodo) e risponde per percorso.
- Il DB di prova puo essere usato anche da altre copie: tabelle estranee (es. activity_*) fanno fallire test_data_registry; riprovare.
- La suite completa dura circa 9 minuti. `config` e un dataclass congelato: nei test si sostituisce `ca.config`.
- Rifiuto di accesso = `AccessoNegato` (CheckFailure) risposto da `handle_app_command_error`.
- Il defer pubblico lascia un messaggio con flag `loading`: va cancellato prima del followup effimero.
- Cache impostazioni: test con SQL grezzo su guild_config devono fare `db._settings_cache.clear()` (clean_db lo fa).
- Ogni tabella nuova va in `core/data_registry.py`: il test di completezza legge lo schema vero e fallisce.
- Ogni colonna `user_id`/`owner_id`/`*_by` nuova va dichiarata (colonne_utente o colonne_attore).
- Migrazioni gia applicate in un DB di prova non si rieseguono se le modifichi: cancella la riga da schema_migrations.
- Una chiave esterna nuova rompe i test di altre aree che inseriscono righe orfane: controllare prima.
- discord.py: per le stringhe il massimo sta in `Parameter.max_value`.
- Un test che esegue una migrazione a mano su `clean_db` sporca il DB condiviso (es. 0010 rimette l'indice vecchio): ripristinare nel finally.
- Esportazione: mai `colonne_attore`; i campi con id di staff escono None. Nuova colonna di stato in un cog che scrive casi: aggiornare 0050-style e il test AST degli action_type.
- Numeri migrazione: mod usa 0040-0041; core ha preso 0050 (verificare la scheda prima della prossima).
- Colonna con id di un bot (non persona) non si chiama `*_user_id`: il test del registro dati la vuole dichiarata (usa `bot_account_id`).
- Comando staff dentro un gruppo pubblico (`utility`): `@richiedi(Livello.ADMIN)` su ogni comando + `@autocomplete_protetto`.
- Migrazione applicata e poi rinominata: `delete from schema_migrations where version=N` e drop della tabella nel DB di prova.
- `monkeypatch.undo()` in un test con `clean_db` annulla anche il pool: ripristinare il singolo attributo.
- Il token OAuth, gli state e i corpi delle risposte Discord non vanno mai in log o messaggi.

## Aperto
- Conteggio caratteri: `admin` 6.4xx su 6.800 (soglia): il prossimo comando admin richiede un nuovo gruppo (D25) o va in un gruppo piu leggero.
- #136 (`/config export` null), #141 e #138 (giri a parte), #135 `reset_premium_registry`.
- 14.13 codice morto (continuo), 14.14 lingue (F8). KNOWN_SENZA_MAX_LENGTH: 27 voci in cogs di altre aree.
- #148: manca solo il picker dei ruoli che chiama `imposta_ruolo` (il link e la callback ci sono).
- Clan sciolto dalla cancellazione: categoria/canali Discord restano da togliere a mano.
- Worker musicale da solo non controlla la blacklist all'ingresso (solo il principale).
