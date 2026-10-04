# HANDOFF_GROK.md — Riepilogo delle correzioni fatte nella sessione del 28 settembre 2026

Documento di passaggio per chi riprende il lavoro (Grok o altri). Elenca
cosa è stato corretto, come, e come è stato testato. Il dettaglio
completo resta in `PIANO_FIX.md`, `REVIEW.md`, `PROGRESS.md` e
`VERIFICA_LIVE.md`. Le regole di processo sono in `CLAUDE.md` (vincolanti).

Nessun segreto è presente in questo file né nei commit citati.

## Metodo usato per ogni voce

1. Lettura della voce in `PIANO_FIX.md` e `REVIEW.md`.
2. Test scritto prima del fix (dove possibile), controllando che
   fallisca per il motivo giusto.
3. Fix minimo, senza riscrivere codice non coinvolto.
4. Test nuovo, poi suite completa (`python3 -m pytest -q`) **due volte**,
   entrambe verdi.
5. Aggiornamento di `PIANO_FIX.md`, `PROGRESS.md`, `VERIFICA_LIVE.md`.
6. Commit in italiano, autore `Yokai Bot Dev`, solo `Refs #N`
   (mai `Closes`/`Fixes`), poi `git push` e controllo che lo SHA locale
   e quello remoto coincidano.

Un test verde **non** è una verifica live: ogni voce che lo richiede ha
i suoi passi in `VERIFICA_LIVE.md`, ancora da eseguire dall'owner.

## Correzioni fatte

| Voce | Commit | Cosa è stato fatto | Come è stato testato |
|---|---|---|---|
| SEC-13 | `8a96320` | `/owner eval` e `/owner shell` spenti di default in produzione (`ENABLE_EVAL`, default calcolato da `ENVIRONMENT`). Log scritto prima dell'esecuzione (`log_started` / `mark_result`), `defer()` prima di eseguire, il timeout dello shell uccide davvero il processo. | Test sul default di configurazione e sui tre comandi. Suite 2205/2205. |
| SEC-14 | `0e9eb3b` | Server web in ascolto su `127.0.0.1` (nuovo `WEB_BIND_HOST`). Server webhook avviato solo se esiste almeno un webhook. Nuovo `core/webhook_rate_tracker.py`: oltre 10 richieste/minuto per token risponde 429. | Test su configurazione, repository, rate tracker e handler (429 oltre il limite). Corretto un inquinamento tra test con una fixture che svuota il tracker. Suite 2215/2215. |
| SEC-15 | `bf2a772` | `aiohttp>=3.13.3` dichiarato (CVE note sotto quella versione), rimosso `structlog` inutilizzato, generato `requirements.lock` con `pip-compile`, README aggiornato. | Nessun test possibile sul pinning: `pip install --dry-run` e suite 2215/2215. |
| SEC-16 | `2df2265` | `field(repr=False)` su tutti i campi segreti di `Config` e sui token OAuth del restore, così un `print(config)` non li mostra. | Test che verificano che nessun segreto compaia in `repr()` e che i valori restino leggibili per nome. Suite 2221/2221. |
| #41 | `576f155` | `PREMIUM_ALPHA_UNLOCK_ALL` falso di default in produzione, con WARNING all'avvio se acceso. | Test su default e override esplicito. Suite 2226/2226. |
| #36 (parte R0) | `3666a66` | Log INFO all'avvio con gli intent realmente attivi di ogni bot (`_elenco_intent_attivi`). Con questo R0 è completa. | Test sulla funzione. Suite 2228/2228. |
| DB-1 / #25 | `659d9fa` | Nuovo pacchetto `core/migrations/` con migrazioni numerate, tabella `schema_migrations`, `pg_advisory_lock` e una transazione per migrazione. `Database.run_migrations()` e `tests/conftest.py` non duplicano più le ~40 chiamate. Prima migrazione `0001_db2_indici.sql` (DB-2): tolti due indici mai usati su `event_log`, aggiunti due indici parziali per query orarie su `clans` e `leveling_totals`. | 9 test in `tests/test_migrations.py`: ordine, applicazione unica, nessuna riesecuzione, due runner concorrenti, rollback su errore, effetti reali della migrazione. Suite 2237/2237. |
| BUG-1 / #2, #42 | `6c724d3` | `/ticket close` andava in crash perché `TextChannel.delete()` non accetta `delay`. L'attesa di 10 secondi è ora una coroutine (`_elimina_dopo`) lanciata come task tracciato in un set del cog e cancellato in `cog_unload`. | 6 test in `tests/test_ticket_close_deletion.py` con `fake_text_channel()` autospec (riproduce lo stesso `TypeError` del bot vero) e un test end-to-end sul comando. Suite 2243/2243. |

I commit di documentazione associati sono `f9d867b`, `c7ca43b`, `9ab5ba3`,
`a6e8db2`, `3934aa1`, `334fc88`, `6b1090a`, `5d27763`.

## Da sapere

- **Da verificare live** (l'owner, con Discord/database/Lavalink veri): tutte
  le voci sopra hanno i loro passi in `VERIFICA_LIVE.md`.
- **Segnalazione per l'owner (SEC-16):** nella storia git di
  `.env.example` c'è una vecchia password Postgres di esempio. Se era reale
  va cambiata. La storia git non è stata riscritta.
- **Nota su DB-1:** il piano parlava di `core/migrations.py` e di
  `core/migrations/`, che non possono coesistere. Si è scelto un pacchetto
  `core/migrations/` con il runner in `__init__.py`.
- **Non fatto:** in `main.py` non ci sono test sull'orchestrazione
  dell'avvio (assenti anche prima).
- **Deviazione dal ciclo:** per SEC-15, #41 e #36 il codice è stato scritto
  prima dei test (o non era testabile). I test sono stati aggiunti subito dopo.

## Stato e prossimo passo

R0 e DB completate. R1 avviata: BUG-1 chiuso. La prossima voce nell'ordine
del piano è **BUG-2** (`/setup` diviso per categoria, #4/#38/#43/#49),
non ancora iniziata (solo lettura del codice). Attenzione: il modulo `fun` è
registrato due volte (`cogs/fun/ship_rate.py` ed `entertainment.py`), 33
registrazioni per 32 moduli unici. La tabella delle categorie dell'issue #49
non è stata consultata.

Divieti da ricordare: nessun nuovo comando top-level prima di R5 (97/100),
nessun nuovo sotto-comando in `/owner` (25/25), nessuna riscrittura della
storia git, nessun segreto nel repository.
