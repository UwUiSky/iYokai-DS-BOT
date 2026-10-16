# Memoria di cacciatore-bug

## Aggiornata
16/10/2026 · ultimo giro: `feat/r7mod` (iYokai Mod, catalogo log, NF-30 DM), 5 fix; i 2 lasciati li ha chiusi il revisore.

## In corso
- Niente a metà.

## Fatto
- Giri 28/09–11/10 (BUG-19…34, SEC-18…22, F1, boost-146, f7, sicurezza-audit, 147, 66, giro-logt/eco/mod): dettagli in `rapporti/bug.md`.
- giro-core, r3-bak, r3-mus, r4-tkt, r4-uti, r4-liv: alti e medi in `rapporti/bug.md` (13/10). Prove in scratchpad/cb{core,bak,mus,tkt,uti,liv}.
- r6mod (5 fix), r6ai (9516f7c; lasciati: tetto/quota funzione in gara tra persone, prefissi in -chiedi), r6web.
- r7mod: forum-cache col client di Mod, blocco di 1 msg via Mod, archivio 20k senza tetto, bottone NF-30 ripetuto/ModMail, cache LOG-017 leggi-poi-set.

## Cose imparate
- Due client (Mod/principale): ogni oggetto in cache porta il SUO client; cache condivise separate per bot. `http.*` via Mod salta i casi speciali di discord.py (1 messaggio…).
- Stato solo in memoria: chi lo svuota (evento spento, richiesta privacy NF-04, riavvio).
- Azioni fatte DAL bot non le vede l'anti-nuke (attore = bot): serve un tetto proprio.
- Difetti frequenti: leggi-poi-scrivi su saldi/contatori; cache "leggi, poi set" con await in mezzo (serve una versione); risposte oltre i limiti; azioni fallite riportate come riuscite.
- Test di corsa: `tests/support/concorrenza.apri_connessioni`, sempre provati togliendo il fix (mutazione in scratchpad). Fake `AsyncMock(side_effect=lambda: asyncio.sleep())` NON aspetta: serve `async def`.
- AI: lavoro automatico che conta sulla persona = aggirabile; niente cache per somiglianza su traduzioni/giudizi.
- Web: `Referrer-Policy: no-referrer` manda `Origin: null` nei POST; `del_cookie` senza `secure=` non cancella `__Host-`.
- Lavori nello scheduler legati all'ingresso: cancellarli al rientro. Controllare anche l'ordine di avvio.
- wavelink: `Pool.connect` torna CONNECTING; provare con un finto Lavalink aiohttp.
- Ordine dei blocchi (clan, batch FOR UPDATE ORDER BY): provare due cicli in parallelo, righe in ordine inverso.
- Router: un UPSERT dal ripiego rende permanente la riga; guardare dopo il cambio del generale.
- Anonimizzare a valore fisso incontra indici unici parziali; registro NF-04: coprire gli action_type dei cog. Ogni tabella nuova: `tests/test_data_registry.py`.
- Regex degli admin: provare `a?`xN+`a`xN, `a{0,99}`xN, `.*.*x$` con timeout.
- Ogni `on_message` con `guild is None` (ModMail, appelli) vede lo STESSO DM: cercare i coordinamenti.
- Ambiente: DB di prova condiviso (`pgrep pytest` prima di fidarsi); prove nei `tests/` con file temporanei poi spostati in scratchpad; cog con `registra_comandi_del_cog(...)`; permessi veri con `discord.Guild/Member(data=..., state=ConnectionState(...))`.

## Aperto
- r4-tkt: rilievi senza fix in `rapporti/bug.md` (13/10); dopo i fix ripetere p1-p8 di cbtkt.
- Giro mod: lo stato si salva PRIMA dell'azione irreversibile; UPSERT su membro già in stato = perdita dati.
- Rami nuovi: confrontare i numeri di migrazione con gli altri rami aperti; unire i rami r4 in una copia di prova.
- Valori scelti da un utente nelle sostituzioni a catena: `escape_mentions` se `roles=True`.
