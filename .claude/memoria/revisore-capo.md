# Memoria di revisore-capo

## Aggiornata
01/11/2026 · `feat/r13ruoli` (D60): merge main (D61), 4 fix (61052f4, 0a029de, 4e96294, test admin-livelli); 2 basse aperte. Smoke da fare: 0488, cerca-comando, ai_ricerca.
01/11/2026 · `feat/r13gruppi` (D56 riordino, D57 livelli, 0485–0487): merge di main, 5 fix (4907600, 56fab94, 680e80e, c3e860f, f14859e) + test sui percorsi nuovi (0441060). 4 aperte nel quaderno. Smoke da fare: migrazioni, quindi suite completa (orchestratore).
01/11/2026 · r12 (lingue, aifree, ai, resto, piatt): tutti APPROVATI dopo i fix (commit nel quaderno); basse aperte nel quaderno.
Giri r6–r11: tutti APPROVATI dopo i fix; basse aperte nel quaderno. `f7-quadro` APPROVATO, manca l'unione.

## In corso
- Niente. Al prossimo giro: righe aperte del quaderno per il ramo riconsegnato.

## Fatto
- Letti per intero: giro-mod, r3–r13 (commit nel quaderno).

## Cose imparate
- Riordino a regex: tabelle di percorsi SENZA `/` (es. COMANDI_VICINI) e sotto-comandi già vecchi sfuggono; confronto albero base/HEAD (livello, permesso, autocomplete) con uno script di dump; scansione `/percorso` contro l'albero vero.
- Riordino dei comandi: i test cercano i percorsi in molti modi (`get_command` a catena, `comando_nel_gruppo(g, f"…")`, `percorsi_del_gruppo`, insiemi ATTESI). Scansione con la tabella della migrazione su tutti i test, poi le corse. Controlli scritti nel corpo (`puo_usare`) sfuggono ai test che leggono solo `.checks`.
- Corse lunghe: `-v --tb=no -rf` (righe man mano), mai `timeout` esterno (niente riepilogo); due metà su due database propri; `pkill -f` col proprio comando: usare `[.]`.
- Lingue: `testo_per` senza `pubblica=True` = lingua personale; embed costruiti a pezzi li trova `tests/test_i18n_pubblica.py`. `comandi.en.json`: "nomi" per SEGMENTO, "descrizioni" per percorso; modificarlo a testo (json.dumps cambia il rientro).
- Controllare il contenuto di ogni commit, non il messaggio; testi che promettono una funzione vanno confrontati col codice; voci `[x]` col catalogo e col test citato (D18).
- Ambiente: `source` dello script env in ogni bash, mai riavviare postgres, database proprio per ramo. Regola owner: niente smoke né suite, «smoke da fare» nel rapporto. Commit senza righe di attribuzione (CLAUDE.md del ramo).
- Merge di main: conflitti nei documenti e in `comandi.en.json`; `COMMAND_LIST*` con `scripts/generate_command_list.py` (errore finale innocuo; se cambia solo la data, scartare).
- Migrazioni per NOME: mai modificarle; numeri confrontati su tutti i rami (`git ls-tree`). Test di una migrazione: `read_text()` ed `execute`, due volte (rilancio).
- `db._…` usate da un cog = manca una funzione pubblica. `SETTING_X` in `SETTINGS_SCHEMA`; tabelle in `core/data_registry.py`; metodi senza chiamanti rompono `test_repository_callers.py`.
- Mutazioni: test scritto prima del fix e visto rosso; script con `str.replace` contato. Test appeso: `asyncio.wait_for`.
- Doppio clic: `asyncio.gather` con `tests/support/concorrenza.apri_connessioni`; segno sincrono prima del primo await. Compiti differiti: un cambio durante il lavoro in corso deve chiedere un altro giro.
- Validare tutto PRIMA del primo salvataggio. Task per chiave: uno solo, fermato in `cog_unload`. Giri con `LIMIT`: righe mai chiuse bloccano le altre.
- Finti: `member.roles` vivo; `fake_member` ha `Permissions.none()`; `Thread.permissions_for` = padre; `monkeypatch.setattr(asyncio, "sleep")` è globale.
- `AllowedMentions(roles=...)` ha `everyone=True`. Azioni automatiche: tetto = ciò che può fare il moderatore (D28, D29). Bot secondari (D15); App utente: `guild_id=None`.
- Regex native Discord 10×260; jolly ripetuti = tempo esponenziale.
- AI: `pulisci_dati_personali` verso servizi non AI; filtro «addestra» in `scegli_fornitori` (D55). File di esempio con segnaposto: il caricatore li scarta.

## Aperto
- Domande all'owner: SPEC 23.16, D18 limite ticket per utente, primo DM ModMail, D27, IPv4 = basso (NF-21), D29, SIC-045.
- r13: due sistemi premium (core/premium.py e livelli_funzione), da decidere (D16).
