# Memoria di revisore-capo

## Aggiornata
01/11/2026 · `feat/r12lingue` (NF-06 #77, ~2.500 frasi nel catalogo it/en): cacciatore + revisione. Merge di main (99654ab: livelli, report, risposte ticket). Corretti testi pubblici nella lingua personale (28b10df, 90 testi, `tests/test_i18n_pubblica.py`). SPEC 21.1/21.6 restano `[~]`.
01/11/2026 · `feat/r12piatt`: APPROVATO (795142b, 530fd71, fb65019, 56a4538, ffec881), 4 basse.
29/10/2026 · `feat/r12resto`: APPROVATO (1adb71f, d13b332, 9e3b497, 21dd796, 9abe0f3, eb25a2c).
Giri r7–r11 (mod, bak, liv, inviti, aiw, odio, util, eco, tkt): tutti APPROVATI, basse aperte nel quaderno.

## In corso
- `feat/r12lingue`: rapporto all'orchestratore; smoke da fare. 3 basse nel quaderno.
- Rami più vecchi: solo le righe aperte del quaderno alla riconsegna. `f7-quadro` APPROVATO, manca l'unione.
01/11/2026 · `feat/r12aifree` (D54 file dei servizi AI gratuiti, D55 chi addestra come ripiego): cacciatore + revisione. Corretti: test della precedenza ambiente/file (d097c29), indirizzo con ACCOUNT_ID scartato (0aaa9db). APPROVATO, 2 basse nel quaderno; smoke da fare (nessuna migrazione).
01/11/2026 · `feat/r12ai` (§25, 0420–0429): 9 fix, APPROVATO, 5 basse; smoke da fare (migrazioni: suite completa).
01/11/2026 · `feat/r12resto` (D48–D51, 0480–0484) e `feat/r12piatt` (D45–D47, 0450–0452): APPROVATI dopo i fix (commit nel quaderno); smoke da fare (suite completa).
Giri r6–r11: tutti APPROVATI dopo i fix; basse aperte nel quaderno.

## In corso
- Niente. Al prossimo giro: righe aperte del quaderno per il ramo riconsegnato.
- `feat/r12ai` 5 basse, `feat/r11eco` 3 basse; migrazioni 0410/0420–0429: suite completa a fine giro (orchestratore). `f7-quadro` APPROVATO, manca l'unione.

## Fatto
- Letti per intero: giro-mod, r3–r12 (commit nel quaderno).

## Cose imparate
- Lingue: `testo_per` senza `pubblica=True` = lingua personale. Embed costruiti a pezzi e poi mandati in pubblico/canale/log sfuggono a chi guarda solo la riga dell'invio: li trova `tests/test_i18n_pubblica.py` (segue le variabili). Controllo «italiano identico»: confrontare ogni valore nuovo di it.json con le stringhe (f-string normalizzate) del file alla base del merge.
- Suite di 257 file di test: oltre 30 minuti. Due metà in parallelo su due database, `run_in_background` con timeout lungo; `pkill -f` con la parola del proprio comando uccide anche sé (usare `[.]`).
- Jolly/glob in regex: cercare i pezzi da sinistra (lineare). Voci `[x]`: confrontare con catalogo e VOCI_OMESSE; aprire il test citato.
- Avvisi per canale: thread = permessi del padre; thread privato = membri/owner/manage_threads; `get_channel_or_thread`.
- Stato globale per (server, utente): fixture autouse che lo pulisce. Segnali «fatto» DOPO l'invio.
- safe_open_image può dare un'immagine senza `format`: il formato si legge dal file.
- Regex native Discord: 10×260; `\b` non scatta dopo un simbolo. AI giudice: testo intero, JSON rigido.
- Controllare il contenuto di ogni commit, non il messaggio; un testo che promette una funzione va confrontato col codice.
- Ambiente: `source` dello script env in ogni bash; mai riavviare postgres; database proprio per ramo. Niente smoke né suite: solo test dei file toccati, «smoke da fare».
- Merge di main: conflitti nei documenti, `comandi.en.json` ("nomi" per SEGMENTO), `COMMAND_LIST*` con `scripts/generate_command_list.py` (errore finale innocuo).
- `db._…` da un cog = manca funzione pubblica. `SETTING_X` in `SETTINGS_SCHEMA`; tabelle in `core/data_registry.py`; metodi senza chiamanti rompono `test_repository_callers.py`.
- Migrazioni per NOME, mai modificarle; numeri e D di DECISIONI confrontati su tutti i rami (`git ls-tree`).
- Mutazioni: copia o `git stash push -m <tag>` + apply per SHA; meglio test scritto prima del fix e visto rosso. Test appeso: `asyncio.wait(..., timeout=)`.
- Doppio clic: `asyncio.gather` con `tests/support/concorrenza.apri_connessioni`; segno sincrono prima del primo await.
- Finti: `member.roles` vivo; `fake_member` con `Permissions.none()`; `monkeypatch.setattr(asyncio, "sleep")` è globale. Risposta cambiata in embed/file: cercare tutti i test dei comandi toccati.
- `AllowedMentions(roles=...)` ha `everyone=True`. Azioni automatiche da un moderatore: tetto = ciò che lui può fare (D28, D29).
- Bot secondari (D15): cercare ogni azione chiamata sul principale. App utente: `is_guild_integration()` falso = saltare le cose del server.
- Comandi con più opzioni: tutti i controlli PRIMA del primo salvataggio. Giri con `LIMIT`: righe mai chiuse bloccano le altre.
- Controllare il contenuto di ogni commit, non il messaggio; testi che promettono una funzione vanno confrontati col codice; voci `[x]` col catalogo e col test citato (D18).
- Ambiente: `source` dello script env in ogni bash, mai `cd` nello script, mai riavviare postgres, database proprio per ramo. Regola owner: niente smoke né suite, solo test dei file toccati (pytest lunghi in background), «smoke da fare» nel rapporto. `test_config_import_validation.py` è lento: non serve per l'area AI.
- Merge di main: conflitti nei documenti e in `comandi.en.json`; `COMMAND_LIST*` con `scripts/generate_command_list.py`; D di DECISIONI confrontati su tutti i rami.
- Migrazioni per NOME: mai modificarle; numeri confrontati su tutti i rami (`git ls-tree`). Test di una migrazione: `read_text()` ed `execute`.
- `db._…` usate da un cog = manca una funzione pubblica. `SETTING_X` in `SETTINGS_SCHEMA` + `test_config_import_validation.py`; tabelle nuove in `core/data_registry.py`; metodi senza chiamanti rompono `test_repository_callers.py`.
- Mutazioni: script in scratchpad con `str.replace` contato e ripristino (`python3 -I`); un test di precedenza deve avere valori pieni da tutte e due le parti.
- Doppio clic: `asyncio.gather` con `tests/support/concorrenza.apri_connessioni`; segno sincrono prima del primo await. Test instabili: due letture dello stesso stato; mai due pytest sullo stesso database.
- Task per chiave: uno solo, fermato in `cog_unload`. Stato in memoria: chi lo svuota, riavvio. Giri con `LIMIT`: righe mai chiuse bloccano le altre.
- Creazione in due passi / comandi con più opzioni: validare tutto PRIMA del primo salvataggio. Tasse: per eccesso. Colonna che sostituisce una vecchia: riempirla nella migrazione.
- Finti: `member.roles` vivo; `fake_member` ha `Permissions.none()`; `Thread.permissions_for` = padre; thread privati a parte; `monkeypatch.setattr(asyncio, "sleep")` è globale.
- `AllowedMentions(roles=...)` ha `everyone=True`. Azioni automatiche: tetto = ciò che può fare il moderatore (D28, D29). Bot secondari (D15): cercare ogni azione sul principale; App utente: `guild_id=None`.
- Regex native Discord 10×260; jolly ripetuti = tempo esponenziale. Risposta cambiata in embed/file: cercare tutti i test del comando.
- AI: testo degli utenti verso servizi non AI con `pulisci_dati_personali`; lavoro AI nei flussi Discord in un compito a parte; cache su disco: chi chiama la pulizia. D55: filtro «addestra» in `scegli_fornitori`, la cache non manda testo fuori (ok servirla ai server «senza_messaggi»).
- File di esempio con segnaposto (ACCOUNT_ID ecc.): il caricatore deve scartarli, non accettarli.
- Statistiche «in una settimana»: GROUP BY per periodo. Liste da mostrare: tetto e «e altre N».

## Aperto
- Domande all'owner: SPEC 23.16, D18 limite ticket per utente, primo DM ModMail, D27, IPv4 = basso (NF-21), D29, SIC-045.
