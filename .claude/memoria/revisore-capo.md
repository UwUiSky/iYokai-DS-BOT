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
