# Memoria di revisore-capo

## Aggiornata
22/10/2026 · ramo `feat/r9mod` (#59 ripiego, M 1.10 warn manuali 0250, `/mod opzioni`, lock a tempo, `/mod caso attive`, SIC-040): corretti i 3 lasciati del cacciatore (D29: scala dei warn manuali solo con permessi e gerarchia del moderatore, mai kick/ban in massa; timeout mai accorciato; lock fisso + lock a tempo si sblocca). Esito smoke nel rapporto.

## In corso
- `feat/r9mod`: nessuna riga aperta. D29 da segnalare all'owner.
- `feat/r8web`: da far confermare all'owner «IPv4 da solo = basso» (VERIFICA_LIVE r8).
- `feat/r8uti`: 1 bassa (schede canale/permessi senza controllo «vede il canale»).
- `feat/r7mod`: aperti noti in SPEC/REGISTRO (log via webhook, invito in /setup, LOG-029). `_shared.py:192` non riconosce Mod come «il bot stesso» (bassa).
- `feat/r7liv`: 3 basse nel quaderno; sfondo per tutti da confermare all'owner.
- `feat/r6mus`: 1 bassa (nome playlist non normalizzato).
- Rami in attesa di riconsegna (righe nel quaderno): `feat/r4-tkt` 23, `feat/r4-uti` 21, `feat/r4-liv` 9, `feat/r3-mus` 8, `feat/r3-bak` 8, `giro-mod` 12, `giro-logt` 11, #66 12, #67 8, #147 6, #76 5+7, #146, #134, #135/#136. `f7-quadro`: APPROVATO, manca l'unione. Alla riconsegna: solo le righe aperte.
- Aperti bassi: r6ai (ticket staff, pacchetto, riassumi doppio, vietate); r6mod `/antiraid segnala` senza tetto.

## Fatto
- Letti per intero: giro-mod, r3-bak, r3-mus, r4-liv, r4-tkt, r4-uti, r6ai, r6mod, r6web, r6mus, r7bak, r7mod, r7liv, r8uti, r8web, r9mod.

## Cose imparate
- Controllare il contenuto di ogni commit, non il messaggio. Testo all'utente che promette una funzione va confrontato col codice.
- Ambiente: `source /tmp/claude-0/env_<ramo>.sh` in ogni bash; `python3 -m pytest`; mai `cd` dentro lo script env.
- Funzioni private `db._…` usate da un cog = manca una funzione pubblica. Più blocchi: controllare TUTTI i punti sulle stesse tabelle.
- Chiavi `SETTING_X` in `SETTINGS_SCHEMA` (o solo owner: `CHIAVI_SOLO_PROPRIETARIO`); `test_config_import_validation.py`. Tabelle nuove in `core/data_registry.py`; metodi di repo senza chiamanti rompono `test_repository_callers.py`.
- Migrazioni tracciate per NOME: una modificata non si riapplica. Cambi = migrazione nuova; confrontare i numeri di tutti i rami (anche le D di DECISIONI, con `git show <ramo>:`).
- Mutazioni: su COPIA del file, script `python3 -I` in scratchpad con `str.replace` contato e ripristino. Test che si blocca con la mutazione: `asyncio.wait(..., timeout=)`.
- Test con id piccoli e `str(x) in str(righe)`: falsi rossi da timestamp. Confrontare i valori.
- Doppio clic / blocchi: `asyncio.gather` con `tests/support/concorrenza.apri_connessioni`; blocco tolto senza test rosso = test mancante.
- Task programmati per chiave: uno solo per chiave, riferimento tenuto, fermati in `cog_unload`.
- Finti: `member.roles` vivo non prova un'istantanea vecchia; `Permissions.all()` per admin; `fake_member` ha `Permissions.none()` di base; `timed_out_until` va letto con `getattr` + `isinstance`.
- Suite completa >10 min: mai. Smoke in background con `nohup` e ciclo `until`; `pkill -f` col testo del comando uccide la propria shell.
- `AllowedMentions(roles=...)` ha `everyone=True` di default. `monkeypatch.undo()` toglie anche il pool del DB. `monkeypatch.setattr(asyncio, "sleep")` è globale.
- Bot secondario (D15): cercare OGNI azione della sua area ancora chiamata sul principale.
- `locales/comandi.en.json` "nomi" è per SEGMENTO, globale; categorie nuove in `etichette_categoria`.
- Azioni automatiche partite da un moderatore (scala, ruoli che aprono livelli): tetto = ciò che lui può fare (D28, D29). Le azioni in massa non devono sfuggire ai tetti MOD-002.
- Ripristini (unlock, scadenze): un «no» salvato come «permesso di prima» lascia bloccato. Stessa regola per unlock a mano e scheduler.

## Aperto
- Domande all'owner: SPEC 23.16 (sfondo solo colore), D18 limite ticket per utente, conferma primo DM ModMail, D27, IPv4 = basso (NF-21), D29.
