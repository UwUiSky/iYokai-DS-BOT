# Memoria di revisore-capo

## Aggiornata
14/10/2026 · ramo `feat/r4-tkt` (674e3b0) #84/#104/#119/#120/#127/#139: DA SISTEMARE (23 righe nel quaderno del ramo)

## In corso
- `feat/r4-tkt` (674e3b0): DA SISTEMARE. Alte: ModMail `_menu_aperti` mai ripulito alla scadenza del menu (utente bloccato fino al riavvio); regex del log: schema ammesso da 284 ms, 5 insieme 1,4 s sul loop (rete a 50 ms tardiva); risposte standard tengono nome utente se il membro è uscito e telefoni/IBAN con spazi. Medie: `modmail_blocks` `cancella` all'oblio (precedente `verify_blacklist` conserva); D18 limite ticket per utente fisso a 1; `rispondi`/`nascondi` senza defer; URL allegati con scadenza; `_chiudi` ModMail senza annullo. Alla riconsegna controllare solo quelle. Smoke 774 verdi; 45 mutazioni (11 sopravvissute: 10, 16, 23, 24, 29, 33, 34, 36, 37, 40, 41), scratchpad/mut/run.py, copia pulita da confrontare con `diff -rq`.
- Altri rami in attesa, vedi il quaderno di ciascuno: `feat/r3-mus` (8 righe, 70 mutazioni), `feat/r3-bak` (8 righe, 53 mutazioni), `giro-mod` 12, `giro-logt` 11, #66 12, #67 8, #147 6, #76 5+7, #59/#117 2, #146, #134, #135/#136 (`remove_member`). `f7-quadro`: APPROVATO, manca l'unione.

## Fatto
- F1 del 05/10 unito (`7722b71`, `3758f2a`, `9db9e8a`). Letti per intero: giro-mod, r3-bak (2596 righe), r3-mus, r4-tkt (6626 righe).

## Cose imparate
- Cambio "giusto" può peggiorare un'altra area: controllare il contenuto di ogni commit, non il messaggio.
- DB per processo (wrevisore3, wrevisore3b per le prove) per non avere fallimenti a caso. `python3 -m pytest`. Il DB vuole `postgres:testpass@127.0.0.1`; servono anche `YOKAI_BOT_TOKEN`/`YOKAI_CREATOR_TOKEN` finti.
- Funzioni private `db._…` usate da un cog = manca una funzione pubblica. Più blocchi: controllare TUTTI i punti che bloccano le stesse tabelle.
- Chiavi `SETTING_X`/`KEY_*` nuove vanno in `SETTINGS_SCHEMA`; tabelle nuove in `core/data_registry.py` (provare con oblio + esportazione; precedente per blocchi/blacklist: `conserva`).
- Mutazioni: `WHERE guild_id = $1` → `$1::bigint IS NOT NULL`; `str.replace(..,1)`; fare il giro su una COPIA (tar, niente rsync) e `diff -rq` con la pulita; `pkill -f` col testo del comando uccide la propria shell; blocchi in background con `nohup` e poll.
- `Permissions(view_channel=False)` ha anche manage_messages=False. Doppio clic / blocchi: `asyncio.gather` con `tests/support/concorrenza.apri_connessioni`; un blocco per chiave A non protegge un vincolo su chiave B.
- Suite completa >10 min: non lanciarla. Smoke ~8 min se il resto è fermo. Voci già a posto sul base: `git show base:file`.
- Task che riprovano per sempre bloccano chi fa `gather`: provare con gestore vero e nodo morto.
- Testo all'utente che promette una funzione va confrontato con ciò che il codice fa davvero.
- Regex scritte da admin: `re` non ha timeout. Fuzz con `signal.setitimer` per schema; schemi con un `*` e 4 `?` costano centinaia di ms su 500 caratteri. Rete a tempo = dopo il danno.
- Stato in memoria (`_menu_aperti`, `_REGEX_DISATTIVATE`, dizionari per canale): chiedersi chi lo ripulisce alla scadenza; provare con `view.stop()` e un secondo messaggio.
- Test che leggono `dati.get(...)` su export: la struttura vera è `dati["tabelle"][nome]["righe"]`; asserzioni vuote passano sempre. Test «altro server»: accendere il modulo anche lì, sennò esce dal controllo sbagliato.
- Privacy: dati ripuliti con i nomi del membro in cache falliscono se il membro è uscito (on_member_remove chiude il ticket subito); prendere i nomi dagli autori dei messaggi.

## Aperto
- giro-mod sopravvissute: vedi quaderno di quel ramo. `fix/f1-135` attende `remove_member`. r4-tkt: domande all'owner su D18 (limite ticket per utente) e su conferma del primo DM ModMail.
