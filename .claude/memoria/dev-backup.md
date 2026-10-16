# Memoria di dev-backup

## Aggiornata
15/10/2026 · ramo `feat/r7bak` · base `e935178` · DB `iyokai_wr7bak` · migrazioni 0190–0192 usate (0193–0199 libere)

## In corso
Giro r7 chiuso: 6 voci su 6 previste, più 12.16. Niente a metà. Prossimo giro, in quest'ordine:
1. SPEC 11.17: aggiornamento continuo del server di backup (differenze periodiche di ruoli, canali, permessi; D8).
2. #113 iYokai Mod (serve l'owner). 3. Revisione del cacciatore-bug sul giro r7 (sincronia, caricamento in sottofondo).

## Fatto
- r7 (15/10): `/backup` gruppo di primo livello (D25 quarto caso) + 12.12/12.14 consenso a fine verifica (1945d35, 0190);
  copie datate, carica con menu delle parti, stato/annullo, esporta/importa, modelli, permessi, registro (8b63130, 0191);
  sincronia ban/ruoli (001a4cb, 0192); copia-canale/ruolo (778ef1b); chat salvate, allegati come file, fissati (3f6f7d5);
  messaggi nella copia datata + registro di tutti i comandi (4310aa8); 12.16 invito rifiutato (1b7db69).
- Fino al 13/10: #68 12.1–12.11, 12.13, 12.15 (collegamento con codice, clonazione da modello, Creator senza create_guild,
  rinnovo token, 429, chiave ruotabile), copia messaggi D8, correzioni del cacciatore-bug e del revisore-capo.

## Cose imparate
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

## Aperto
- 11.17 aggiornamento continuo del backup non fatto. Copia messaggi D8 e tutto il giro r7: da provare live (VERIFICA_LIVE «Backup — giro r7»).
- La proposta di consenso in DM (verifica a reazione) usa una View non persistente: dopo un riavvio i bottoni non rispondono (15 minuti).
- Chat salvate: nome, avatar e testo dei messaggi dentro `backup_strutture.dati`: la cancellazione per utente (NF-04) non li tocca, vanno via con la copia o col server (nota nel registro dati).
- `main.py` on_guild_join: Main entra nel server di backup prima del collegamento e riceve il trattamento "server nuovo" (dev-core).
- `core/command_groups.py` e `tests/test_command_groups.py` (non miei) toccati per il gruppo `/backup` (D25): avvisare dev-core.
- #113 iYokai Mod: non fatto (serve l'owner).
