# Memoria di revisore-capo

## Aggiornata
02/11/2026 · `feat/r15automod` (D63 A1–A8, #116): main già unito, 10 fix (c9a9dee, c9852c0, 885acee, 389201c, 28c12c9, 4284b22, 79138ab, c2b1a65, 1e4c79f, 23e00c8) + documenti 535d5d1; 7 basse aperte. APPROVATO. Smoke da fare: test_automod_*, immagini_cog, 0500–0503, tree_invariants, riferimenti, i18n.
02/11/2026 · `feat/r15immagini` (D62/D63, #153): main già unito, 10 fix (sandbox attesa, no ripiego dopo lavoro preso, worker senza Pillow, staff controllati, malevola = timeout, solo malevole in libreria, cache/libreria, 72 h, gruppo systemd, docstring). APPROVATO. Smoke da fare: test_immagini_*, migrazioni 0504–0506, riferimenti.
02/11/2026 · `feat/r15vpn` (D64, D65, 0507, 0508, #155): merge main (0b07b2f), 6 fix (e5e4774, 14568f1, a895a2c, 9ff3e96, 38ec7c5, 72e1fed); 6 basse/medie aperte nel quaderno. APPROVATO. Smoke da fare: 0507, 0508, verify_vpn*, panel_bridge, panel_proprietario, modmail, data_registry, aggiorna_vpn.
01/11/2026 · `feat/r14lingue` (D58, #77): main già unito, 5 fix (5afa1c1, 5fc82bf, fb493e7, 7a66e08, 6f3a7a3); 4 basse aperte. APPROVATO. Smoke da fare: i18n, translator, lingue_struttura, cerca-comando.
01/11/2026 · `feat/r14paese` (D53, 0490): merge main (becf64f), 4 fix (fde536c, 9462b25, 735d4a0, a7b0cd3); 4 basse aperte. APPROVATO. Smoke da fare: 0490, verify, panel_bridge.
Giri r6–r13: tutti APPROVATI dopo i fix (commit e basse nel quaderno). `f7-quadro` APPROVATO, manca l'unione.

## In corso
- Niente. Al prossimo giro: righe aperte del quaderno per il ramo riconsegnato.

## Fatto
- Letti per intero: giro-mod, r3–r13 (commit nel quaderno).

## Cose imparate
- Stati decisi dallo staff (attesa/rifiuto) si leggono PRIMA di ogni uscita anticipata (dato mancante = porta aperta). Soglie a conteggio: salvare poi contare. Il ramo senza issue: `Refs D<n>`, mai un numero a caso.
- Riordino a regex: tabelle di percorsi SENZA `/` (es. COMANDI_VICINI) e sotto-comandi già vecchi sfuggono; confronto albero base/HEAD (livello, permesso, autocomplete) con uno script di dump; scansione `/percorso` contro l'albero vero.
- Riordino dei comandi: i test cercano i percorsi in molti modi (`get_command` a catena, `comando_nel_gruppo(g, f"…")`, `percorsi_del_gruppo`, insiemi ATTESI). Scansione con la tabella della migrazione su tutti i test, poi le corse. Controlli scritti nel corpo (`puo_usare`) sfuggono ai test che leggono solo `.checks`.
- Corse lunghe: `-v --tb=no -rf` (righe man mano), mai `timeout` esterno (niente riepilogo); due metà su due database propri; `pkill -f` col proprio comando: usare `[.]`.
- Lingue: `testo_per` senza `pubblica=True` = lingua personale; embed costruiti a pezzi li trova `tests/test_i18n_pubblica.py`. `comandi.en.json`: "nomi" per SEGMENTO, "descrizioni" per percorso; modificarlo a testo (json.dumps cambia il rientro).
- Controllare il contenuto di ogni commit, non il messaggio; testi che promettono una funzione vanno confrontati col codice; voci `[x]` col catalogo e col test citato (D18).
- Ambiente: `source` dello script env in ogni bash, mai riavviare postgres, database proprio per ramo. Regola owner: niente smoke né suite, «smoke da fare» nel rapporto. Commit senza righe di attribuzione (CLAUDE.md del ramo).
- Database di test condiviso con altri agenti = fallimenti a caso (tabelle di altri rami, righe sparite): rifare la corsa su un database proprio creato e poi tolto.
- Elenchi scaricati: reindirizzamenti https→http (urllib li segue) e reti enormi (0.0.0.0/0) da scartare. Righe aggiunte a messaggi pubblici: `testo_guild`.
- Diff di `.gitignore` e file di configurazione: leggerli sempre (una riga fusa coi commenti smette di ignorare `.env`); test con `git check-ignore --no-index`.
- Merge di main: conflitti nei documenti e in `comandi.en.json`; `COMMAND_LIST*` con `scripts/generate_command_list.py` (errore finale innocuo; se cambia solo la data, scartare).
- Migrazioni per NOME: mai modificarle; numeri confrontati su tutti i rami (`git ls-tree`). Test di una migrazione: `read_text()` ed `execute`, due volte (rilancio).
- `db._…` usate da un cog = manca una funzione pubblica. `SETTING_X` in `SETTINGS_SCHEMA`; tabelle in `core/data_registry.py`; metodi senza chiamanti rompono `test_repository_callers.py`.
- Mutazioni: test scritto prima del fix e visto rosso; script con `str.replace` contato. Test appeso: `asyncio.wait_for`.
- Doppio clic: `asyncio.gather` con `tests/support/concorrenza.apri_connessioni`; segno sincrono prima del primo await. Compiti differiti: un cambio durante il lavoro in corso deve chiedere un altro giro.
- Validare tutto PRIMA del primo salvataggio. Task per chiave: uno solo, fermato in `cog_unload`. Giri con `LIMIT`: righe mai chiuse bloccano le altre.
- Finti: `member.roles` vivo; `fake_member` ha `Permissions.none()`; `Thread.permissions_for` = padre; `monkeypatch.setattr(asyncio, "sleep")` è globale.
- `AllowedMentions(roles=...)` ha `everyone=True`. Azioni automatiche: tetto = ciò che può fare il moderatore (D28, D29). Bot secondari (D15); App utente: `guild_id=None`.
- Sandbox: ogni attesa del figlio dentro il tempo vero; dopo che il servizio ha preso il lavoro, niente ripiego più debole; uscita >0 da interprete rotto ≠ malevola. Unità systemd: mai il gruppo del bot al servizio (il PNG torna nei log = canale di fuga).
- Regex native Discord 10×260; jolly ripetuti = tempo esponenziale.
- Motore azioni: 403 su chi Discord non lascia toccare (proprietario, ruolo ≥ bot) non è un permesso mancato: niente sospensione per server. Finti: posizione 0 = raggiungibile. «Applica» dello staff = il bot agisce per lui: permessi di ogni sanzione + gerarchia. Soglie: scatta solo chi consuma (UPDATE conta righe).
- AI: `pulisci_dati_personali` verso servizi non AI; filtro «addestra» in `scegli_fornitori` (D55). File di esempio con segnaposto: il caricatore li scarta.

## Aperto
- Domande all'owner: SPEC 23.16, D18 limite ticket per utente, primo DM ModMail, D27, IPv4 = basso (NF-21), D29, SIC-045.
- r13: due sistemi premium (core/premium.py e livelli_funzione), da decidere (D16).
