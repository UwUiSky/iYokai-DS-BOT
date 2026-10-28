# Memoria di revisore-capo

## Aggiornata
28/10/2026 · `feat/r10liv` (livelli/economia r10: SPEC §15 a `[x]`, shop 0340, classifica settimanale, moneta e tassa 0341). Fatto anche il cacciatore. Corretti: minimo pay (0342) e tassa per eccesso (b1c1f45); righe shop controllate prima, codice in DM, scadenze solo server del bot (f92d597); registro (485e139). APPROVATO, smoke da fare.

## In corso
- `feat/r10liv`: 3 basse aperte nel quaderno (categorie maiuscole, emoji del server nel nome moneta, `{utente}`). Migrazione 0342 nuova: suite completa a fine giro (orchestratore).
- `feat/r10musa`: 4 basse aperte; D30 da segnalare all'owner. `feat/r10amod`: 3 basse. `feat/r10util`: 2 basse (owner via VERIFICA_LIVE).
- Altri rami: righe aperte nel quaderno (r9nsfw, r8web IPv4, r8uti, r7mod `_shared.py:192`, r7liv, r6mus, r6ai, r6mod). Rami in attesa di riconsegna: righe nel quaderno. `f7-quadro` APPROVATO, manca l'unione. Alla riconsegna: solo le righe aperte.

## Fatto
- Letti per intero: giro-mod, r3-*, r4-*, r6*, r7*, r8*, r9nsfw, r9mod, r10amod, r10util, r10bak, r10musa, r10liv (commit nel quaderno).

## Cose imparate
- Controllare il contenuto di ogni commit, non il messaggio. Voci SPEC a `[x]`: confrontare con il catalogo (`revisione/01-analisi/catalogo/`, riga del codice ECO/LIV) se la funzione è completa (D18).
- Ambiente: `source` dello script env in ogni bash; mai riavviare postgres; database proprio per ramo. Regola owner: niente smoke né suite dagli agenti, solo i test dei file toccati, «smoke da fare» nel rapporto.
- Merge di main: conflitti nei documenti e in `comandi.en.json` ("nomi" per SEGMENTO, globale; menu in `menu`); `COMMAND_LIST*` con `scripts/generate_command_list.py`.
- `db._…` usate da un cog = manca una funzione pubblica. Chiavi `SETTING_X` in `SETTINGS_SCHEMA`; tabelle nuove in `core/data_registry.py`; metodi di repo senza chiamanti rompono `test_repository_callers.py`.
- Migrazioni per NOME: mai modificarne una; numeri confrontati su tutti i rami (`git ls-tree` per ramo remoto).
- Peso dei gruppi (D25): script con `_albero_vero`/`conta_caratteri` di `tests/test_command_tree_invariants.py`.
- Mutazioni: su copia; meglio test scritto prima del fix e visto rosso. Test che si blocca: `asyncio.wait(..., timeout=)`.
- Doppio clic: `asyncio.gather` con `tests/support/concorrenza.apri_connessioni`. Test instabili: due letture dello stesso stato.
- Giri periodici con `LIMIT`: righe che non si chiudono mai (server lasciato) bloccano le altre; filtrare o chiudere.
- Creazione in due passi (oggetto, poi dati): validare tutto PRIMA del primo passo.
- Arrotondamenti di tasse/percentuali: per difetto si evitano spezzando; per eccesso.
- Task per chiave: uno solo, fermati in `cog_unload`. Finti: `member.roles` vivo; `_FakeGuild` senza `name`; `monkeypatch.setattr(asyncio, "sleep")` è globale.
- `AllowedMentions(roles=...)` ha `everyone=True` di default. Azioni automatiche da un moderatore: tetto = ciò che lui può fare (D28, D29).
- Bot secondario (D15); App utente (`is_guild_integration()` falso = salta ciò che è del server).

## Aperto
- Domande all'owner: SPEC 23.16, D18 limite ticket per utente, primo DM ModMail, D27, IPv4 = basso (NF-21), D29, D30, addio + ban doppio, emoji del server come nome moneta.
28/10/2026 · `feat/r10sec` (VER-017/019/020/030/031, SIC-036, SIC-039, PERF-3, SPEC §4/§7 a `[x]`). Fatto anche il giro del cacciatore. Corretti: niente ruolo senza verifica durante un raid, «solo sospetti» rispetta l'età minima, «attendi» non punisce il clic presto, posto libero per canali trappola cancellati (a115efd); COMMAND_LIST (d396ce3). APPROVATO; smoke da fare (regola owner).

## In corso
- `feat/r10sec`: 3 basse aperte nel quaderno (import canali extra senza tetto, ora CSV consumata su errore, `_livello_al_raid` su istantanea). SIC-045 serve una scelta dell'owner.
- `feat/r10musa`: 4 basse aperte; D30 da segnalare. `feat/r10amod`: 3 basse. `feat/r10util`: 2 basse da far decidere all'owner.
- Altri rami: r9nsfw 1 bassa, r8web IPv4 da confermare, r8uti 1 bassa, r7mod `_shared.py:192`, r7liv 3 basse, r6mus 1 bassa, r6ai, r6mod `/antiraid segnala` senza tetto. Rami in attesa di riconsegna: righe nel quaderno. `f7-quadro` APPROVATO, manca l'unione.

## Fatto
- Letti per intero: giro-mod, r3-*, r4-*, r6*, r7*, r8*, r9nsfw, r9mod, r10amod, r10bak, r10util, r10musa, r10sec (commit nel quaderno).

## Cose imparate
- Controllare il contenuto di ogni commit, non il messaggio. Voci SPEC passate a `[x]`: cercare nel codice ogni bug dello «Stato» (tabella §3/§4 di `MODIFICHE_ESISTENTE.md`).
- Ambiente: `source` dello script env in ogni bash; mai riavviare postgres; mai `$VAR` vuota nei percorsi. Smoke e suite: mai (regola owner), solo i test dei file toccati.
- Comandi o opzioni nuovi: rigenerare `COMMAND_LIST*` con `scripts/generate_command_list.py` (errore finale innocuo) e controllare `comandi.en.json` ("nomi" per SEGMENTO, globale).
- `db._…` usate da un cog = manca una funzione pubblica. Chiavi `SETTING_X` in `SETTINGS_SCHEMA` + `test_config_import_validation.py`; l'import non applica i tetti dei comandi. Tabelle nuove in `core/data_registry.py`; metodi senza chiamanti rompono `test_repository_callers.py`.
- Migrazioni: mai modificarne una; numeri (e D di DECISIONI) confrontati su tutti i rami.
- Mutazioni: copia in scratchpad, `python3 -I` con `str.replace` contato, ripristino. Meglio: test scritto prima del fix e visto rosso.
- Doppio clic: `asyncio.gather` con `tests/support/concorrenza.apri_connessioni`. Test instabili: due letture dello stesso stato.
- Task per chiave: uno solo, fermati in `cog_unload`. Stato in memoria: chi lo svuota, riavvio.
- Finti: `member.roles` vivo; `Thread.permissions_for` = padre; `monkeypatch.setattr(asyncio, "sleep")` è globale.
- Sicurezza: ogni scorciatoia che dà un ruolo senza verifica va spenta durante `raid_in_corso` (gli allow dei ruoli battono i deny della quarantena) e non deve saltare l'età minima. Un'azione «attendi» va rispettata anche dagli altri percorsi (azione su chi non passa).
- Liste di ID scelte con un selettore: un oggetto cancellato non si può più togliere, ripulire gli ID morti.
- Azioni automatiche da un moderatore: tetto = ciò che lui può fare (D28, D29). `AllowedMentions(roles=...)` ha `everyone=True`.
- Bot secondario (D15) e App utente (`is_guild_integration()` falso = salta ciò che è del server).
- Opzioni testo «vuoto = togli»: Discord non manda testi vuoti, serve «-».

## Aperto
- Domande all'owner: SPEC 23.16, D18 limite ticket per utente, primo DM ModMail, D27, IPv4 = basso (NF-21), D29, D30, SIC-045 (opt-out raccolta di rete).
