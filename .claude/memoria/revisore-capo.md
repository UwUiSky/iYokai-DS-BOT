# Memoria di revisore-capo

## Aggiornata
28/10/2026 · `feat/r11odio` (D35/D39, 0390+0391): fatto anche il cacciatore. Corretti: regex native con varianti e prefissi comuni, testo intero all'AI e niente AI per testi manipolati, risposta rigida, AI ferma senza richiamo, blocco fallito non resta acceso, libreria a proprietari diversi + parole comuni (vedi commit). APPROVATO, smoke da fare (migrazione 0391: suite completa).
28/10/2026 · `feat/r10liv` (livelli/economia r10: SPEC §15 a `[x]`, shop 0340, classifica settimanale, moneta e tassa 0341). Fatto anche il cacciatore. Corretti: minimo pay (0342) e tassa per eccesso (b1c1f45); righe shop controllate prima, codice in DM, scadenze solo server del bot (f92d597); registro (485e139). APPROVATO, smoke da fare.
28/10/2026 · ramo `feat/r10inviti` (link personali, D32, 0380): fatti anche i controlli del cacciatore; fix 8b9426b (permesso del membro, canale pubblico, tetto 500, verifica invito vivo, race tracker), d45c4f2 (COMMAND_LIST). APPROVATO con 4 basse nel quaderno; smoke da fare.
28/10/2026 · `feat/r10aiw` (#95 AI r10, 0350–0351): APPROVATO dopo i fix: comandi AI aperti in prova (b302da0, `richiede_ai`), prova non ripetibile dopo la purga (0be178a, `ai_prove`), elenco comandi (c2b8c98). Smoke da fare (regola owner: lo lancia l'orchestratore). Aperte 2 basse nei quaderni.
21/10/2026 · ramo `feat/r8tkt` (#120 opzioni ticket, #139 AI, migrazione 0220): merge di main (991f977); corretti presa esclusiva/passa/rilascia e note archiviate (bd26b6d), cache opzioni (ad83893), reperibili ricontrollati; test instabile dei due close = doppia lettura in `close`. Esito smoke nel rapporto.
16/10/2026 · r7mod, r7bak (3be8a40), r7liv.

## In corso
- `feat/r10liv`: 3 basse aperte nel quaderno (categorie maiuscole, emoji del server nel nome moneta, `{utente}`). Migrazione 0342 nuova: suite completa a fine giro (orchestratore).
- `feat/r10musa`: 4 basse aperte; D30 da segnalare all'owner. `feat/r10amod`: 3 basse. `feat/r10util`: 2 basse (owner via VERIFICA_LIVE).
- Altri rami: righe aperte nel quaderno (r9nsfw, r8web IPv4, r8uti, r7mod `_shared.py:192`, r7liv, r6mus, r6ai, r6mod). Rami in attesa di riconsegna: righe nel quaderno. `f7-quadro` APPROVATO, manca l'unione. Alla riconsegna: solo le righe aperte.

## Fatto
- Letti per intero: giro-mod, r3-*, r4-*, r6*, r7*, r8*, r9nsfw, r9mod, r10amod, r10util, r10bak, r10musa, r10liv (commit nel quaderno).

## Cose imparate
- Regex native Discord: 10×260 caratteri; prefissi comuni (albero) e niente `\w*` finale fanno spazio; `\b` non scatta dopo un simbolo in fondo. AI come giudice: niente testo tagliato (insulto in coda), JSON rigido, soglie «N server» = N proprietari.
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
28/10/2026 · ramo `feat/r10filtro` (#116 AMD-014, parole vietate): fatto anche il lavoro del cacciatore; corretti aggiramenti, lecite che spegnevano la base, parola in più messaggi, scala per chi gestisce, giro dei nomi (1669138). Smoke da fare (regola owner: solo test dei file toccati).

## In corso
- `feat/r10filtro`: 2 basse aperte nel quaderno; da scrivere in DECISIONI (orchestratore): «una voce di base non può diventare lecita».
- `feat/r9nsfw`: 1 bassa (tetto promemoria letto-poi-scritto). `feat/r8web`: «IPv4 da solo = basso» da confermare. `feat/r8uti`: 1 bassa.
- `feat/r7mod`: aperti noti in SPEC/REGISTRO; `_shared.py:192` (bassa). `feat/r7liv`: 3 basse. `feat/r6mus`: 1 bassa.
- In attesa di riconsegna (righe nel quaderno): r4-tkt, r4-uti, r4-liv, r3-mus, r3-bak, giro-mod, giro-logt, #66, #67, #147, #76, #146, #134, #135/#136. `f7-quadro` APPROVATO, manca l'unione.
- Aperti bassi: r6ai per dev-ai; r6mod `/antiraid segnala` senza tetto.

## Fatto
- Letti per intero: giro-mod, r3-bak, r3-mus, r4-liv, r4-tkt, r4-uti, r6ai, r6mod, r6web, r6mus, r7bak, r7mod, r7liv, r8tkt, r8uti, r8web, r9mod, r9nsfw, r10filtro.

## Cose imparate
- Controllare il contenuto di ogni commit, non il messaggio; testi che promettono una funzione vanno confrontati col codice.
- Ambiente: `source` dello script env in ogni bash; mai riavviare postgres se l'orchestratore lo vieta; mai `cd` dentro lo script env.
- Chiavi `SETTING_X` in `SETTINGS_SCHEMA` (solo owner: `CHIAVI_SOLO_PROPRIETARIO`) + `test_config_import_validation.py`; tabelle nuove in `core/data_registry.py`; migrazioni per NOME, numeri contro tutti i rami.
- Mutazioni: copia del file, `str.replace` contato, test, ripristino (script in scratchpad). Test appeso: `asyncio.wait(..., timeout=)`.
- Liste lecite/eccezioni: controllare che non spengano ciò che ha un interruttore protetto (conferma, solo owner).
- Filtri di testo: provare varianti a mano (omoglifi lisu/cherokee, riempitivi hangul, U+202E, censura `*`, parola spezzata, più messaggi); tetti di lavoro aggirabili con pezzi civetta: meglio un indice che un tetto.
- Soglie di tempo nei test: 0,5 s (sotto carico 0,1 s fallisce).
- Heredoc con `\uXXXX` in Python: nel file finiscono caratteri veri; riconvertire in escape (bidi invisibili nel sorgente).
- Doppio clic: `asyncio.gather` con `tests/support/concorrenza.apri_connessioni`; task per chiave: uno solo, fermato in `cog_unload`.
- Finti: `member.roles` vivo non prova un'istantanea; `fake_member` ha `Permissions.none()`; `create_autospec(discord.PartialMessage)` per i messaggi da cancellare per id.
- `AllowedMentions(roles=...)` ha `everyone=True` di default. `monkeypatch.setattr(asyncio, "sleep")` è globale.
- Bot secondario (D15): ogni azione dell'area chiamata sul principale.
- `locales/comandi.en.json` "nomi" è per SEGMENTO, globale; menu del tasto destro in `menu`.
- Azioni automatiche da un moderatore: tetto = ciò che lui può fare (D28, D29). Scale automatiche: chi gestisce il server fuori.
- App utente: `is_guild_integration()` falso = salta tutto ciò che è del server.
- Inviti creati dal bot per un membro: permesso «Crea invito» DEL MEMBRO nel canale, canale visibile a @everyone, tetto 1000/server; la cache del tracker non sa delle cancellazioni (INVITE_DELETE solo con Gestisci canali).
- Controllare il contenuto di ogni commit, non il messaggio. Testo all'utente che promette una funzione va confrontato col codice.
- Ambiente: `source /tmp/claude-0/env_<ramo>.sh` in ogni bash; `python3 -m pytest`; mai `cd` dentro lo script env; mai `cat > $VAR_VUOTA` (aspetta stdin). Postgres giù dopo un riavvio: `service postgresql start` e attendere il recupero (`pg_isready`).
- Merge di main: conflitti a due lati nei documenti e in `comandi.en.json` (unire, controllare chiavi doppie); `COMMAND_LIST*.md` si rigenerano.
28/10/2026 · `feat/r10logt` (log, ticket chiusi 0302, vocali 0300–0301): fatto anche il lavoro del cacciatore. Corretti 031a2d3 (ticket chiusi), a8866f8 (D34 log ignora), ea2f070 (generatore privato), 33030a3 (indice 0303, SPEC 8.8), afee66f (elenco comandi). APPROVATO; smoke da fare dall'orchestratore.

## In corso
- `feat/r10logt`: aperti nel quaderno 1 media (`/log cerca ruolo` senza ruoli dati/tolti, per dev-log-ticket) e 3 basse. D34 da segnalare all'owner. Al merge: D34 numerato dall'orchestratore (D31–D33 riservati); COMMAND_LIST da rigenerare.
- `feat/r9nsfw`: 1 bassa (tetto promemoria letto-poi-scritto). `feat/r8web`: «IPv4 da solo = basso» da far confermare all'owner. `feat/r8uti`: 1 bassa.
- `feat/r7mod`: aperti noti in SPEC/REGISTRO; `_shared.py:192` Mod non «il bot stesso» (bassa). `feat/r7liv`: 3 basse. `feat/r6mus`: 1 bassa. `feat/r8tkt`: 1 bassa accettata.
- Rami in attesa di riconsegna (righe nel quaderno): r4-tkt, r4-uti, r4-liv, r3-mus, r3-bak, giro-mod, giro-logt, #66, #67, #147, #76, #59/#117, #146, #134, #135/#136. `f7-quadro` APPROVATO, manca l'unione.
- Aperti bassi: r6ai per dev-ai; r6mod `/antiraid segnala` senza tetto.

## Fatto
- Letti per intero: giro-mod, r3-bak, r3-mus, r4-liv, r4-tkt, r4-uti, r6ai, r6mod, r6web, r6mus, r7bak, r7mod, r7liv, r8tkt, r8uti, r8web, r9mod, r9nsfw, r10logt.

## Cose imparate
- Controllare il contenuto di ogni commit, non il messaggio. Voci passate a `[x]`: aprire il test citato e vedere che prova QUELLA voce (r10: 8.8 citava LC-6 con un testo sbagliato).
- Ambiente: `source` dello script env in ogni bash; `python3 -m pytest`; mai riavviare postgres se l'orchestratore lo vieta. Regola owner r10: niente smoke né suite, solo test dei file toccati.
- Merge di main: conflitti nei documenti e in `comandi.en.json` (chiavi doppie); `COMMAND_LIST*.md` si rigenerano (`scripts/generate_command_list.py`; gli errori dei task alla chiusura sono innocui).
- Funzioni private `db._…` usate da un cog = manca una funzione pubblica. Più blocchi: controllare TUTTI i punti sulle stesse tabelle.
- Chiavi `SETTING_X` in `SETTINGS_SCHEMA` (solo owner: `CHIAVI_SOLO_PROPRIETARIO`); `test_config_import_validation.py`. Tabelle nuove in `core/data_registry.py`; metodi di repo senza chiamanti rompono `test_repository_callers.py`.
- Migrazioni tracciate per NOME: una modificata non si riapplica. Numeri: confrontare con `git ls-tree main core/migrations/` e gli altri rami; anche le D di DECISIONI con `git show main:`.
- Mutazioni: su COPIA del file, script `python3 -I` in scratchpad con `str.replace` contato e ripristino. Test scritto prima del fix e visto rosso vale come prova.
- Test instabili di corsa: cercare DUE letture dello stesso stato nello stesso comando.
- Doppio clic / blocchi: `asyncio.gather` con `tests/support/concorrenza.apri_connessioni`.
- Task programmati per chiave: uno solo per chiave; annullarli quando lo stato torna indietro (riapertura ticket → `scheduler.cancel_for_channel`).
- Finti: `member.roles` vivo non prova un'istantanea vecchia; `Permissions.all()` per admin; `fake_member` ha `Permissions.none()`; `canale.overwrites` va impostato a mano nei finti.
- Stato/cache in memoria: chi lo svuota, cosa succede al riavvio; limite accettato → VERIFICA_LIVE.
- Chiavi `SETTING_X` in `SETTINGS_SCHEMA` (quelle di permessi anche in `CHIAVI_SOLO_PROPRIETARIO`); tabelle nuove in `core/data_registry.py`; metodi di repo senza chiamanti rompono `test_repository_callers.py`. Migrazioni: confrontare i numeri di tutti i rami.
- Mutazioni: su COPIA del file (cp in scratchpad, `python3 -I` con `str.replace`, poi ripristino).
- Test instabili di corsa: cercare DUE letture dello stesso stato nello stesso comando; test deterministico con una lettura finta che cambia lo stato dopo la prima.
- Doppio clic / blocchi: `asyncio.gather` con `tests/support/concorrenza.apri_connessioni`; blocco tolto senza test rosso = test mancante.
- Presa esclusiva / ruoli self-service / reperibili: ricontrollare i permessi al momento dell'uso; chi perde la presa perde i permessi personali.
- Task programmati per chiave: uno solo per chiave, il nuovo annulla il vecchio.
- Finti: `member.roles` vivo non prova un'istantanea vecchia; `Thread.permissions_for` eredita dal padre; thread archiviati non in `get_thread`; `create_autospec(discord.Thread)` per `isinstance`. `Pool.fetchrow` è sola lettura: finto sul `_pool_provider`.
- Suite completa >10 min: mai. Smoke in background con `nohup` e poll ≤119 s; `pkill -f` col testo del comando uccide la propria shell.
- Stato/cache in memoria: chi lo svuota, versione contro leggi-poi-set, cosa succede al riavvio. `AllowedMentions(roles=...)` ha `everyone=True` di default.
- Bot secondario (D15): cercare OGNI azione della sua area ancora chiamata sul principale.
- Prove gratuite/sblocchi temporanei: controllare TUTTI i cancelli (decoratori `requires_module` compresi) e cosa sopravvive alla purga del server.
- `locales/comandi.en.json` "nomi" è per SEGMENTO, globale: una chiave nuova rinomina ogni comando con quel nome.
- Ruoli che aprono un livello più alto: chi li sceglie deve avere quel livello (D28). Ripristini fatti dal bot: tetto = ruolo più alto di chi lancia.
- DECISIONI: i «casi» di D25 aggiunti da rami diversi vanno numerati contro `git show main:`.
- Stato in memoria: chi lo ripulisce, cosa succede al riavvio; se limite accettato -> VERIFICA_LIVE.
- `AllowedMentions(roles=...)` ha `everyone=True` di default. `monkeypatch.undo()` toglie anche il pool del DB.
- `locales/comandi.en.json` "nomi" è per SEGMENTO, globale: una chiave nuova rinomina ogni comando con quel nome.
- Ruoli che aprono un livello più alto: chi li sceglie deve avere il permesso di quel livello (D28). Caricamenti fatti dal bot: tetto = ruolo più alto di chi lancia.
- Limiti per IP del pannello: un secchio per funzione (accesso, verifica), non condiviso.
- Chiavi `SETTING_X` in `SETTINGS_SCHEMA` (o `SETTINGS_SOLO_OWNER` se solo l'owner le cambia: mai importabili); far girare `test_config_import_validation.py`. Tabelle nuove in `core/data_registry.py`; metodi di repo senza chiamanti rompono `test_repository_callers.py`. Migrazioni: confrontare i numeri di tutti i rami.
- Mutazioni: su COPIA del file, script con `python3 -I`, `str.replace` contato. Un test che con la mutazione si blocca va reso finito (`asyncio.wait(..., timeout=)`), non lasciato appeso.
- `monkeypatch.setattr(modulo.asyncio, "sleep", ...)` cambia asyncio.sleep per tutti: per cedere il turno, future + `call_soon`.
- Tetti in memoria globali (`prenota_uso`): azzerarli nella fixture, o i test dopo il secondo falliscono.
- Bot secondario (D15): cercare OGNI azione della sua area ancora chiamata sul principale.
- DECISIONI: i «casi» di D25 vanno numerati e datati contro `git show main:`.
- Chiavi `SETTING_X` in `SETTINGS_SCHEMA` (o solo owner: `CHIAVI_SOLO_PROPRIETARIO`); `test_config_import_validation.py`. Tabelle nuove in `core/data_registry.py`; metodi di repo senza chiamanti rompono `test_repository_callers.py`.
- Migrazioni tracciate per NOME: una modificata non si riapplica. Cambi = migrazione nuova; confrontare i numeri di tutti i rami (anche le D di DECISIONI, con `git show <ramo>:`).
- Mutazioni: su COPIA del file, script `python3 -I` in scratchpad con `str.replace` contato e ripristino. Test che si blocca con la mutazione: `asyncio.wait(..., timeout=)`.
- Test con id piccoli e `str(x) in str(righe)`: falsi rossi da timestamp. Confrontare i valori.
- Doppio clic / blocchi: `asyncio.gather` con `tests/support/concorrenza.apri_connessioni`; blocco tolto senza test rosso = test mancante.
- Task programmati per chiave: uno solo per chiave, riferimento tenuto, fermati in `cog_unload`.
- Finti: `member.roles` vivo non prova un'istantanea vecchia; `Permissions.all()` per admin; `fake_member` ha `Permissions.none()` di base; `timed_out_until` va letto con `getattr` + `isinstance`.
- Suite completa >10 min: mai. Smoke in background con `nohup` e ciclo `until`; `pkill -f` col testo del comando uccide la propria shell.
- `AllowedMentions(roles=...)` ha `everyone=True` di default. `monkeypatch.undo()` toglie anche il pool del DB. `monkeypatch.setattr(asyncio, "sleep")` è globale.
- `locales/comandi.en.json` "nomi" è per SEGMENTO, globale.
- Ruoli che aprono un livello più alto: chi li sceglie deve avere quel livello (D28). Ripristini fatti dal bot: tetto = ruolo più alto di chi lancia.
- Bot secondario (D15): cercare OGNI azione della sua area ancora chiamata sul principale.
- `locales/comandi.en.json` "nomi" è per SEGMENTO, globale; categorie nuove in `etichette_categoria`.
- Azioni automatiche partite da un moderatore (scala, ruoli che aprono livelli): tetto = ciò che lui può fare (D28, D29). Le azioni in massa non devono sfuggire ai tetti MOD-002.
- Ripristini (unlock, scadenze): un «no» salvato come «permesso di prima» lascia bloccato. Stessa regola per unlock a mano e scheduler.
28/10/2026 · ramo `feat/r10core` (wizard a passi, premium sblocca, marchio #109, inviti, 21.1, App B.3/B.4 0360, log webhook D33 0361): cacciatore + revisione. Corretti 42e71d4, c636cb1, 294a604, 3a036cb, 3a56c23, f0513ef. APPROVATO con 5 basse aperte nel quaderno. Smoke da fare (regola owner).

## In corso
- `feat/r10core`: 5 basse aperte (round, nomi inglesi /strumenti, livello con modulo spento, sblocca su modulo già incluso, webhook orfano) per dev-core.
- `feat/r9nsfw`: 1 bassa (tetto promemoria letto-poi-scritto). `feat/r8uti`: 1 bassa. `feat/r8web`: «IPv4 = basso» da far confermare.
- `feat/r7mod`: `_shared.py:192` Mod non «il bot stesso» (bassa). `feat/r7liv`: 3 basse. `feat/r6mus`: 1 bassa. r6ai e r6mod: basse per dev-ai/dev-mod.
- Rami in attesa di riconsegna (righe nel quaderno): r4-tkt, r4-uti, r4-liv, r3-mus, r3-bak, giro-mod, giro-logt, #66, #67, #147, #76, #146, #134, #135/#136. `f7-quadro` APPROVATO, manca l'unione. Alla riconsegna: solo le righe aperte.

## Fatto
- Letti per intero: giro-mod, r3-*, r4-*, r6ai, r6mod, r6web, r6mus, r7*, r8*, r9nsfw, r9mod, r10core.

## Cose imparate
- Controllare il contenuto di ogni commit, non il messaggio; testo che promette una funzione va confrontato col codice. Docstring contro test: un test può fissare il bug (file via webhook).
- Ambiente: `source <env>` in ogni bash; mai riavviare postgres se l'orchestratore lo vieta; mai `cd` nello script env.
- Mutazioni: `git stash -q -- <file>` del solo fix, test, `git stash pop`; oppure copia in scratchpad + `python3 -I` con `str.replace` contato.
- Doppio clic su una vista: `BaseView.interaction_check` attende il DB, quindi `stop()` nel callback NON basta. Segno sincrono prima del primo await; test con `asyncio.gather` di due callback.
- Leggi-poi-scrivi e creazioni (webhook, post) per chiave: blocco per chiave; i blocchi asyncio vanno svuotati nella fixture.
- Bot secondari (Mod, marchio, app): cercare OGNI azione chiamata sul principale; interazioni inoltrate vanno filtrate per server.
- discord.py: un `commands.Bot` non collegato ha `_connection.user` None, un'interazione con `guild_id` lo vuole (impostare un `ClientUser`). Il webhook chiude i `File` anche quando fallisce.
- Chiavi `SETTING_X` in `SETTINGS_SCHEMA` (solo owner: `CHIAVI_SOLO_PROPRIETARIO`); tabelle nuove in `core/data_registry.py`; metodi di repo senza chiamanti rompono `test_repository_callers.py`.
- Migrazioni tracciate per NOME: mai modificarle; numeri confrontati con tutti i rami (anche le D di DECISIONI, `git show main:`).
- `COMMAND_LIST*.md`: `scripts/generate_command_list.py` (l'errore finale «not initialised» è innocuo).
- `locales/comandi.en.json` "nomi" è per SEGMENTO, globale; menu del tasto destro in sezione `menu`.
- Azioni automatiche partite da un moderatore: tetto = ciò che lui può fare (D28, D29).
- App utente: `is_guild_integration()` falso = server senza l'app; le cose del server vanno saltate.
- `AllowedMentions(roles=...)` ha `everyone=True` di default. `monkeypatch.setattr(asyncio, "sleep")` è globale.
- Elenchi con tetto alto (100) in un embed: righe intere e «e altre N», mai un taglio a metà.

## Aperto
- Domande all'owner: SPEC 23.16 (sfondo solo colore), D18 limite ticket per utente, primo DM ModMail, D27, IPv4 = basso (NF-21), D29.
28/10/2026 · ramo `feat/r10mod` (mute a tempo/hardmute/rientro 0270, caso registra, casi esterni, avvisi staff, SPEC §5.1–5.10 [x]): fatto anche il lavoro del cacciatore. Corretti 03c4116, a1b2092, a3587dd, 4ab5dfc, 9885eba. Esito APPROVATO con 2 basse aperte. Smoke da fare (regola owner: solo test dei file toccati).

## In corso
- `feat/r10mod`: 2 basse aperte (quaderno 28/10). Prima dell'unione: merge di main (conflitti solo in documenti e COMMAND_LIST*, poi rigenerare). Smoke unico a fine giro (lo lancia l orchestratore).
- `feat/r9nsfw`: 1 bassa (tetto promemoria letto-poi-scritto).
- `feat/r8web`: «IPv4 da solo = basso» da far confermare all'owner. `feat/r8uti`: 1 bassa (schede senza «vede il canale»). `feat/r8tkt`: 1 bassa (`_ruolo_secondo_ai`).
- `feat/r7mod`: aperti noti in SPEC/REGISTRO; `_shared.py:192` Mod non «il bot stesso» (bassa). `feat/r7liv`: 3 basse, sfondo per tutti da confermare. `feat/r6mus`: 1 bassa.
- Rami in attesa di riconsegna (righe nel quaderno): r4-tkt, r4-uti, r4-liv, r3-mus, r3-bak, giro-mod, giro-logt, #66, #67, #147, #76, #59/#117, #146, #134, #135/#136. `f7-quadro` APPROVATO, manca l'unione. Alla riconsegna: solo le righe aperte.
- Aperti bassi: r6ai per dev-ai; r6mod `/antiraid segnala` senza tetto.

## Fatto
- Letti per intero: giro-mod, r3-bak, r3-mus, r4-liv, r4-tkt, r4-uti, r6ai, r6mod, r6web, r6mus, r7bak, r7mod, r7liv, r8tkt, r8uti, r8web, r9mod, r9nsfw, r10mod.

## Cose imparate
- Controllare il contenuto di ogni commit, non il messaggio; testo all'utente che promette una funzione va confrontato col codice.
- Ambiente: `source` dello script env in ogni bash; mai riavviare postgres se lo dice la scheda; `python3 -m pytest -p no:cacheprovider`.
- Merge di main: conflitti nei documenti e in `comandi.en.json`; `COMMAND_LIST*.md` si rigenerano (`scripts/generate_command_list.py`, l'errore finale «Client not initialised» è innocuo). Comando nuovo senza elenco rigenerato = rilievo.
- Chiavi `SETTING_X` in `SETTINGS_SCHEMA` (solo owner: `CHIAVI_SOLO_PROPRIETARIO`); `test_config_import_validation.py`. Tabelle nuove in `core/data_registry.py`; metodi di repo senza chiamanti rompono `test_repository_callers.py`.
- Migrazioni tracciate per numero/nome: ordine fuori sequenza va bene, una modificata non si riapplica. Confrontare i numeri di tutti i rami (anche le D di DECISIONI, con `git show main:`).
- Mutazioni: su COPIA, script `python3 -I` in scratchpad con `str.replace` contato e ripristino; più mutazioni in un solo script. Test che si blocca: `asyncio.wait(..., timeout=)`.
- Comandi con più opzioni: tutti i controlli PRIMA di ogni salvataggio, o errore mostrato e metà salvata.
- Membro alla scadenza (scheduler): `trova_membro` (cache poi fetch), mai solo `get_member`.
- Azioni nuove che toccano un utente (anche solo un caso registrato): gerarchia + ruoli immuni (`check_can_moderate`, `azione_su_discord=False` se su Discord non si fa nulla).
- Azioni automatiche partite da un moderatore: tetto = ciò che lui può fare (D28, D29); in massa mai fuori dai tetti MOD-002.
- Ripristini (unlock, scadenze): un «no» salvato come «permesso di prima» lascia bloccato.
- Stato in memoria/cache: chi lo svuota, versione contro leggi-poi-set, cosa succede al riavvio. Task per chiave: uno solo, riferimento tenuto, fermati in `cog_unload`.
- Finti: `member.roles` vivo non prova un'istantanea vecchia; `fake_guild` ha `owner_id=555` e `get_member` None; `Thread.permissions_for` eredita; `create_autospec(discord.Thread)` per `isinstance`.
- `AllowedMentions(roles=...)` ha `everyone=True` di default. `monkeypatch.undo()` toglie il pool; `monkeypatch.setattr(asyncio, "sleep")` è globale. Tetti in memoria globali: azzerarli nella fixture.
- Bot secondario (D15): cercare OGNI azione della sua area ancora chiamata sul principale. App utente: `is_guild_integration()` falso = saltare le cose del server.

## Aperto
- Domande all'owner: SPEC 23.16 (sfondo solo colore), D18 limite ticket per utente, conferma primo DM ModMail, D27, IPv4 = basso (NF-21), D29.
- Filtri «ignora» e nascondere canali: mai eventi di sicurezza fuori dal log (D34); nascondere = tutte le sovrascritture non staff.
