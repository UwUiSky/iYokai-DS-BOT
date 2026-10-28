# Memoria di revisore-capo

## Aggiornata
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
