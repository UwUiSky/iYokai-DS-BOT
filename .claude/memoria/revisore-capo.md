# Memoria di revisore-capo

## Aggiornata
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
