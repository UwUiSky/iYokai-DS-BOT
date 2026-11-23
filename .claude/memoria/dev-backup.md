# Memoria di dev-backup

## Aggiornata
23/11/2026 · ramo `feat/r3bkp` · DB `iyokai_w121` · migrazioni 0950–0951 usate (0952–0959 libere)

## In corso
Giro r3bkp chiuso (BKP-022/023/040, D130): restano la prova live (VERIFICA_LIVE «giro r3bkp») e la revisione del cacciatore-bug.
Giro r10 chiuso: tutte le voci SPEC §11 `[x]` (11.1–11.17). Da fare dopo, in quest'ordine:
1. Prove su Discord (VERIFICA_LIVE «Backup — giro r10» e «giro r7»).
2. #113 iYokai Mod (serve l'owner). 3. Revisione del cacciatore-bug sul giro r10.

## Fatto
- r3bkp (23/11, #121): raccolta pubblica modelli (`core/backup_raccolta_logic.py`, repo, `core/web_panel_raccolta.py`, `/admin-backup raccolta`, `Caricatore(solo_mancanti, pericolosi_ok)`, 0950); BKP-040 interruttore VPN/rete su `/join` senza IP (0951).
- r2bkp (22/11, #121/#132): controllo delle 23+5 voci in `revisione/01-analisi/catalogo/CONTROLLO_AREE_CHIUSE.md`; realizzate BKP-002/006/007/008/020/021/022(pronti)/028, AI-001/004/017; D108 per BKP-022/023/039/040/041, AI-003, AI-010. Ruoli nuovi pericolosi solo se carica l'owner. `lista copia:N` fa da info (admin-backup è a 18 figli).
- r10 (27/10): espressioni senza doppioni, permesso, tetto suoni per boost (11.5-7); forum+stage, riuso sui campi diversi,
  spostamento di categoria (11.4); aggiornamento ogni 6 ore in `backup_queue_worker`, 0320 (11.17); mirror con coda per
  canale e file (11.9); promuovi al livello di carica e mirror tolto (11.13); webhook con immagine (11.8).
- r7 (15/10): `/backup` gruppo (D25), copie datate, sincronia, chat salvate, consenso 12.12/12.14, invito rifiutato.
- Fino al 13/10: #68 12.1–12.15 (codice di collegamento, Creator senza create_guild, rinnovo token, 429, chiave ruotabile).

## Cose imparate
- Un IP non va mai a `verify_vpn_staff.controlla` se non deve restare: usa `verify_vpn.rileva` e scarta. Test «niente IP»: cerca il testo in `row_to_json` di tutte le tabelle.
- Routes web: il test dei comandi citati (`test_riferimenti_comandi`) legge anche le stringhe con `/nome`: scrivere `"/" + "nome"`.
- Migrazioni: file `core/migrations/NNNN_*.sql`; repository in `core/repositories/` (non `repositories/`).
- Il nome `test*` importato in un file di test viene raccolto da pytest: non chiamare funzioni `testo_*`.
- I fake dei test clone sono minimi: dopo ogni nuova chiamata a Discord aggiungere il metodo al fake.
- Test di concorrenza: `apri_connessioni` + `gather`, e controllare l'esito esatto. Fixture del worker: pulire anche `backup_pairs`.
- Metodi di repo senza chiamante rompono `tests/test_repository_callers.py`: aggiungere il comando nello stesso commit.
- Cifrato token: formato `v2.<idchiave>.<b64>`, AAD `guild:utente`; `OAUTH_ENCRYPTION_KEY` può avere più chiavi con virgola.
- `main.py` (non mio) chiama `finalize_backup_job`, `backup_queue_worker.start(creator, bot, perms)`.
- Pesi: script `pesi.py` nella scratchpad; `/backup` 3.794 caratteri (22 comandi) a fine r7, `/admin` 5.502. Traduzioni: `locales/comandi.en.json` (`nomi` globali, `descrizioni` per percorso).
- Caricamenti lunghi: `BackupCog.avvia_lavoro(interaction, fonte, totale, dettaglio, lavoro)` (stato e annullo in `backup_caricamenti`, riepilogo nel canale).
- Registro: `registra_uso` (cogs/utility/backup.py) non fa fallire l'azione se il database non risponde.
- Un file importato è dato non fidato: `valida_struttura` prima di tutto; immagini solo da cdn.discordapp.com / media.discordapp.net.
- Nei fake di discord.py non usare isinstance per i canali: `canale.type` (ChannelType) funziona con oggetti semplici.

- Espressioni: i fake dei test non hanno `me`/`premium_tier`: nel codice `getattr` con valore di ripiego. Il tetto suoni è `tetto_suoni(tier)`.
- Mirror: `BackupMirrorDispatcher._send` è il punto da sostituire nei test; dopo `handle_message` si fa `await dispatcher.svuota()`.
- Aggiornamento continuo: `popola_server_backup(..., con_messaggi=False)`; un test del worker con `popola_server_backup` finto deve accettare `con_messaggi`.

## Aperto
- r3bkp: la revisione dei modelli è solo dal pannello (`/proprietario/modelli`), nessun comando `/owner`. Tocchi fuori area: `core/web_panel_server.py` (2 righe di collegamento), `locales/en-US/comandi.json` (raccolta). La raccolta non ha filtro per lingua nel comando (c'è nel pannello).
- r2bkp: provare live (VERIFICA_LIVE «giro r2bkp»), in particolare la lettura di un vero modello `discord.new` (ruolo @everyone con id 0).
- Pagina backup nel pannello web (BKP-041/022/023): serve dev-web. `test_repository_callers` fallisce per `ticket_form_repo.risposta_questionario` (non mio).
- Giri r7 e r10 da provare live (VERIFICA_LIVE).
- La proposta di consenso in DM (verifica a reazione) usa una View non persistente: dopo un riavvio i bottoni non rispondono (15 minuti).
- Chat salvate: nome, avatar e testo dei messaggi dentro `backup_strutture.dati`: la cancellazione per utente (NF-04) non li tocca, vanno via con la copia o col server (nota nel registro dati).
- `main.py` on_guild_join: Main entra nel server di backup prima del collegamento e riceve il trattamento "server nuovo" (dev-core).
- `core/command_groups.py` e `tests/test_command_groups.py` (non miei) toccati per il gruppo `/backup` (D25): avvisare dev-core.
- #113 iYokai Mod: non fatto (serve l'owner).
