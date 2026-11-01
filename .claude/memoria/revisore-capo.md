# Memoria di revisore-capo

## Aggiornata
01/11/2026 · `feat/r12resto` seconda parte (D51, 0482–0484): cacciatore + revisione. Corretti serie di prima azzerate (0484) e «settimana piena» su settimane diverse (a0d6ab3). APPROVATO; smoke da fare (migrazioni: suite completa). /level e /economia sotto 6800 (test verde).
29/10/2026 · `feat/r12resto` prima parte (D48–D50, 0480–0481): APPROVATO dopo 1adb71f, d13b332, 9e3b497, 21dd796, 9abe0f3, eb25a2c.
28/10/2026 · r11util, r11odio, r11eco, r10 (liv, inviti, aiw, sec, filtro, logt, core, mod): tutti APPROVATI dopo i fix; basse nel quaderno.
Giri r6–r9: APPROVATI, basse aperte nel quaderno.

## In corso
- Niente. Al prossimo giro: righe aperte del quaderno per il ramo riconsegnato.
- `feat/r11eco`: 3 basse nel quaderno. Rami r6–r10: solo le righe aperte. `f7-quadro` APPROVATO, manca l'unione.

## Fatto
- Letti per intero: giro-mod, r3–r11, r12resto (commit nel quaderno).

## Cose imparate
- Colonna nuova che sostituisce una vecchia (es. `ultima_at` al posto di `ultimo_giorno`): la migrazione deve riempirla dalle righe di prima, o i dati veri si azzerano.
- Statistiche dei traguardi «in una settimana/una volta»: contare per periodo (GROUP BY), non il totale.
- Controllare il contenuto di ogni commit, non il messaggio; testi che promettono una funzione vanno confrontati col codice; voci `[x]` col catalogo e col test citato (D18).
- Ambiente: `source` dello script env in ogni bash, mai `cd` nello script, mai riavviare postgres. Regola owner: niente smoke né suite, solo test dei file toccati, «smoke da fare» nel rapporto.
- Migrazioni per NOME: mai modificarle; numeri confrontati su tutti i rami (`git ls-tree` per ramo remoto). Test di una migrazione: `read_text()` del file ed `execute`.
- Peso dei gruppi (D25): `tests/test_command_tree_invariants.py -k caratteri` (lo script a parte non parte: client non inizializzato).
- `db._…` usate da un cog = manca una funzione pubblica. Chiavi `SETTING_X` in `SETTINGS_SCHEMA` + `test_config_import_validation.py`; tabelle nuove in `core/data_registry.py`; metodi senza chiamanti rompono `test_repository_callers.py`.
- Mutazioni: copia in scratchpad o test scritto prima e visto rosso. Test appeso: `asyncio.wait(..., timeout=)`.
- Doppio clic: `asyncio.gather` con `tests/support/concorrenza.apri_connessioni`; INSERT ON CONFLICT + SELECT FOR UPDATE nella stessa transazione regge.
- Giri periodici con `LIMIT`: righe mai chiuse bloccano le altre; filtrare o segnare.
- Creazione in due passi: validare tutto PRIMA del primo passo. Arrotondamenti di tasse: per eccesso.
- Task per chiave: uno solo, fermato in `cog_unload`. Stato in memoria: chi lo svuota, riavvio.
- Finti: `member.roles` vivo; `fake_member` ha `Permissions.none()`; `Thread.permissions_for` = padre; `monkeypatch.setattr(asyncio, "sleep")` è globale.
- `AllowedMentions(roles=...)` ha `everyone=True` di default. Azioni automatiche: tetto = ciò che può fare il moderatore (D28, D29).
- Regex native Discord 10×260; jolly ripetuti = tempo esponenziale. Risposta cambiata in embed/file: cercare tutti i test del comando.

## Aperto
- Domande all'owner: SPEC 23.16, D18 limite ticket per utente, primo DM ModMail, D27, IPv4 = basso (NF-21), D29, SIC-045.
