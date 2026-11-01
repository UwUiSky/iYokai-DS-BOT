# Memoria di revisore-capo

## Aggiornata
01/11/2026 · `feat/r12lingue` (NF-06 #77, ~2.500 frasi nel catalogo it/en): cacciatore + revisione. Merge di main (99654ab: livelli, report, risposte ticket). Corretti testi pubblici nella lingua personale (28b10df, 90 testi, `tests/test_i18n_pubblica.py`). SPEC 21.1/21.6 restano `[~]`.
01/11/2026 · `feat/r12piatt`: APPROVATO (795142b, 530fd71, fb65019, 56a4538, ffec881), 4 basse.
29/10/2026 · `feat/r12resto`: APPROVATO (1adb71f, d13b332, 9e3b497, 21dd796, 9abe0f3, eb25a2c).
Giri r7–r11 (mod, bak, liv, inviti, aiw, odio, util, eco, tkt): tutti APPROVATI, basse aperte nel quaderno.

## In corso
- `feat/r12lingue`: rapporto all'orchestratore; smoke da fare. 3 basse nel quaderno.
- Rami più vecchi: solo le righe aperte del quaderno alla riconsegna. `f7-quadro` APPROVATO, manca l'unione.

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

## Aperto
- Domande all'owner: SPEC 23.16, D18 limite ticket per utente, primo DM ModMail, D27, IPv4 = basso (NF-21), D29, SIC-045.
