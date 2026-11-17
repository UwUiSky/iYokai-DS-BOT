# Regole di sicurezza (vincolanti)

Valgono per ogni riga di codice, di chiunque: persona, Sonnet, Opus o altro.
Chi scrive le applica; chi rivede le controlla una per una sul diff.
Una voce non rispettata blocca l'unione in `main`.

## 1. Tutto ciò che arriva da fuori è ostile

"Da fuori" = testo, nomi, file, link, ID, JSON di utenti, di altri bot, di
servizi esterni e del pannello web.

- **Permessi prima di tutto.** Ogni comando, bottone, menu, finestra e rotta web
  controlla chi chiama **in quel momento** e **su quel server**. Mai fidarsi di
  un ID scritto in un `custom_id`, in un campo nascosto o in un JSON.
- **Gerarchia dei ruoli.** Prima di agire su un membro o un ruolo: il bersaglio
  sta sotto chi comanda **e** sotto il bot. Mai agire sul proprietario del server.
- **Menzioni.** Ogni messaggio con testo di un utente parte con
  `allowed_mentions` esplicito (di norma tutto spento).
- **Testo mostrato.** Nomi e testi di utenti passano dalla pulizia prima di
  finire in embed, log, nomi di canali o di webhook: niente accenti gravi che
  escono dal blocco, niente link mascherati `[x](url)`, niente caratteri di
  controllo o invisibili. Lunghezze sempre tagliate ai limiti di Discord.
- **Espressioni regolari scritte da utenti:** solo con `re2` (mai `re`), con
  tetto di lunghezza.
- **Modelli e script degli utenti** (tag, comandi personalizzati): solo
  l'interprete chiuso che c'è già. Mai `eval`, `exec`, `format` con oggetti veri,
  `getattr` su nomi scelti dall'utente.

## 2. File e allegati (D61, D62, D74)

- Il processo del bot **non apre mai** un file di un utente. Lo apre solo la
  sandbox (`core/immagini_sandbox.py`, `core/conversioni_worker.py`).
- Il tipo si decide **dai primi byte** (`core/allegati_tipo_logic.decidi`), mai
  dal nome o dal content-type.
- L'originale **non si conserva e non si rimanda**. Esce solo la copia rifatta
  (`core/allegati_copia.copia_sicura`) oppure la scheda (nome pulito, tipo, peso).
- Mai mostrare il link di Discord all'allegato originale di un utente.
- Un nome di file non diventa mai un percorso su disco. Sul disco solo nomi casuali.
- Ogni lavoro pesante ha tetti di byte, pixel, pagine, durata, tempo e memoria.
  Ucciso o scaduto = nessuna copia.

## 3. Rete

- Un URL scelto da un utente si scarica **solo** con `core/safe_http`
  (niente reti private, redirect limitati, tetto di byte e di tempo).
- Mai passare a Lavalink, ffmpeg o a un altro programma un URL o un percorso
  non controllato. ffmpeg: lista di argomenti, formato in entrata esplicito,
  `-protocol_whitelist file,pipe`, mai una shell.
- Server HTTP del bot: in ascolto su `127.0.0.1`, dietro un proxy. `X-Forwarded-For`
  vale solo dai proxy fidati.

## 4. Database

- Valori **sempre** come parametri (`$1`, `$2`). In una stringa SQL entrano solo
  nomi di colonna presi da un elenco fisso nel codice, controllati con
  `raise ValueError` (mai con `assert`).
- Ogni tabella con dati personali entra in `core/data_registry.py` (cancellazione,
  copia dei dati, scadenza).
- Operazioni che devono valere una volta sola: transazione, `FOR UPDATE` o
  vincolo unico. Mai "leggo, poi scrivo" senza blocco.

## 5. Segreti

- Nessun segreto in repository, commit, issue, log, messaggi d'errore, URL, chat.
- A riposo: cifrato (`core/oauth_crypto`) se va riletto, solo impronta SHA-256
  se va confrontato. Confronti con `hmac.compare_digest`.
- Nei log l'URL va senza query; i campi segreti di `Config` hanno `repr=False`.
- Il modello `.env.example` parte in `production`, con `eval` e hot patch spenti.

## 6. Pannello web e interfacce HTTP

- Sessione: cookie `__Host-`, HttpOnly, Secure, SameSite=Lax; nel database solo
  l'impronta.
- Ogni scrittura: token CSRF **e** controllo dell'`Origin`.
- Pagine: Jinja con escape automatico, CSP senza script (tranne le eccezioni già
  scritte), mai HTML costruito a mano con dati di utenti.
- Limite di richieste per IP (anonimi) e per utente (loggati), limite sul corpo.
- Un errore non mostra mai dettagli interni.

## 7. Abuso e costi

- Ogni comando che costa (rete, sandbox, AI, database pesante) ha una pausa per
  utente e un tetto per server. `defer()` prima del lavoro lento.
- Liste con tetto o a pagine. Cache e code sempre con un massimo.
- Ciò che un utente può far partire tante volte (reazioni, link, messaggi) non
  deve poter riempire la coda della sandbox né le quote dei servizi esterni.

## 8. Comandi pericolosi

- `/owner eval`, `/owner shell`, caricamento dei cog e hot patch: spenti in
  produzione. Non aggiungerne altri. Niente che esegua codice arrivato da Discord.
- Processi esterni: sempre lista di argomenti, timeout, ambiente ridotto.

## 9. Come si rivede (chi fa l'ultimo controllo)

Per ogni file toccato dal diff, rispondere per iscritto:

1. Da dove entra un dato non fidato? Dove viene controllato?
2. Chi può chiamare questo codice? Il permesso è controllato qui o si dà per scontato?
3. Cosa succede con input vuoto, enorme, ripetuto mille volte, in contemporanea?
4. Cosa succede se il servizio esterno, la sandbox o il database non rispondono?
   (Nel dubbio si deve chiudere: nessun file, nessuna azione.)
5. Qualcosa finisce in un log, in un messaggio o in un file che non dovrebbe?
6. C'è un test che fallisce senza la protezione?

Un difetto trovato si dimostra con un test che fallisce, poi si corregge.

---

# Esempi: la falla, perché è una falla, come si scrive giusto

Ogni esempio viene da un caso vero di questo progetto o da un errore tipico dei
bot Discord. «SBAGLIATO» non va mai scritto; «GIUSTO» è il modello da copiare.

## E1. Il permesso dato per scontato

Un bottone resta cliccabile da chiunque veda il messaggio, anche mesi dopo.

```python
# SBAGLIATO: chi clicca decide chi viene bannato. Il custom_id lo può leggere e rimandare chiunque.
@discord.ui.button(label="Conferma ban", custom_id="ban:conferma")
async def conferma(self, interaction, button):
    await interaction.guild.ban(discord.Object(self.bersaglio_id), reason="confermato")
```

```python
# GIUSTO: si ricontrolla ADESSO chi clicca, su QUESTO server, e la gerarchia.
async def conferma(self, interaction, button):
    autore = interaction.user
    if not autore.guild_permissions.ban_members:
        return await interaction.response.send_message(await testo_per(interaction, "serve_ban"), ephemeral=True)
    bersaglio = interaction.guild.get_member(self.bersaglio_id)
    if bersaglio is not None and (
        bersaglio.id == interaction.guild.owner_id
        or bersaglio.top_role >= autore.top_role          # chi comanda sta sopra il bersaglio
        or bersaglio.top_role >= interaction.guild.me.top_role  # e anche il bot
    ):
        return await interaction.response.send_message(await testo_per(interaction, "gerarchia"), ephemeral=True)
    await interaction.guild.ban(discord.Object(self.bersaglio_id), reason=motivo[:512])
```

**Come ragionare:** «Se questo bottone lo preme l'utente più ostile del server,
tra sei mesi, cosa succede?» Nei gruppi di comandi usa sempre `GruppoYokai`
(un `app_commands.Group` semplice sotto un gruppo protetto non controlla nulla).

## E2. Il ruolo che scavalca

```python
# SBAGLIATO: un moderatore con «Gestisci ruoli» si dà (o dà a un amico) un ruolo sopra il suo.
await membro.add_roles(ruolo)
```

```python
# GIUSTO
if ruolo.managed or ruolo.is_default() or ruolo >= interaction.guild.me.top_role:
    raise RuoloNonAssegnabile("bot")          # il bot non può darlo
if interaction.user.id != interaction.guild.owner_id and ruolo >= interaction.user.top_role:
    raise RuoloNonAssegnabile("gerarchia")    # chi comanda non può dare un ruolo pari o sopra il suo
if ruolo.permissions.administrator and not interaction.user.guild_permissions.administrator:
    raise RuoloNonAssegnabile("amministratore")
```

Vale anche per i ruoli **automatici** (benvenuto, livelli, menu dei ruoli): chi
li configura non deve poter far assegnare dal bot un ruolo che lui stesso non
potrebbe dare. Si controlla quando si salva l'impostazione **e** quando il bot assegna.

## E3. Il testo dell'utente che esce dal suo posto

Caso vero (revisione D74): un nome di file scriveva un link nel log dello staff.

```python
# SBAGLIATO: nome = "a` [premi qui](https://truffa.example) `.txt"
riga = f"`{allegato.filename}` ({kib} KiB)"       # nel log diventa un link cliccabile
await canale.send(f"{utente.display_name} ha scritto: {testo}")   # @everyone, link mascherati, righe finte
```

```python
# GIUSTO: si pulisce, si taglia, e le menzioni sono spente comunque.
from core.allegati_tipo_logic import nome_pulito
riga = f"`{nome_pulito(allegato.filename)}` ({kib} KiB)"
await canale.send(
    testo_sicuro[:2000],
    allowed_mentions=discord.AllowedMentions.none(),
)
```

Dove il testo entra in un embed: `discord.utils.escape_markdown(...)` più il
taglio (titolo 256, descrizione 4096, campo 1024, motivo dell'audit 512).

## E4. Il file aperto dal bot

Caso vero dell'owner: un file travestito da immagine ha rubato gli accessi.

```python
# SBAGLIATO: il tipo lo dice il nome; il bot apre il file; l'originale viene rimandato.
if allegato.filename.endswith(".png"):
    img = Image.open(io.BytesIO(await allegato.read()))     # parser nel processo del bot
await log.send(file=await allegato.to_file())               # originale rimandato com'è
embed.set_image(url=allegato.url)                           # link all'originale
```

```python
# GIUSTO: decisione unica dai byte, lavoro nella sandbox, esce solo la copia rifatta o la scheda.
from core import allegati_mostra
copie, righe = await allegati_mostra.prepara(message.attachments, guild.id)
file = [discord.File(io.BytesIO(dati), filename=f"allegato{i}.png") for i, (_, dati) in enumerate(copie)]
```

**Come ragionare:** «Questo codice tocca i byte di un utente? Allora chi li apre
è la sandbox, e ciò che esce l'ha rifatto la sandbox.» Se la sandbox è giù,
scaduta o risponde storto: **nessun file**, solo la scheda.

## E5. Il vuoto che cancella tutto

Caso vero (musica B3): `/music coda pulisci` con l'elenco dei presenti vuoto
avrebbe svuotato tutta la coda.

```python
# SBAGLIATO: se `canale` è None o la cache non risponde, `presenti` è vuoto e TUTTI risultano assenti.
presenti = {m.id for m in getattr(canale, "members", [])}
da_togliere = [t for t in coda if t.richiedente not in presenti]
```

```python
# GIUSTO: un vuoto che può venire da un errore non autorizza un'azione distruttiva.
if not presenti:
    return await rispondi("Non riesco a leggere chi è nel canale: non ho tolto niente.")
```

Stesso ragionamento per: elenco dei ban vuoto, membri non in cache, risposta
vuota di un servizio esterno, `fetch` fallito. **Nel dubbio non si agisce.**

## E6. Lo stato cambiato prima del controllo

Caso vero (musica B3): il mescola fisso si accendeva anche se il comando falliva.

```python
# SBAGLIATO
player.mescola_fisso = True                 # effetto già avvenuto...
if not ha_brani_suoi:
    return await errore("Non hai abbastanza brani tuoi")   # ...ma all'utente diciamo «errore»
```

```python
# GIUSTO: prima tutti i controlli, poi l'effetto, poi il messaggio che dice la verità.
if not ha_brani_suoi:
    return await errore("Non hai abbastanza brani tuoi")
mescola(coda)
player.mescola_fisso = True
```

## E7. «Leggo, poi scrivo» sui soldi

```python
# SBAGLIATO: due comandi insieme leggono entrambi 100 e spendono entrambi 100.
saldo = await pool.fetchval("SELECT coin FROM profili WHERE user_id=$1", uid)
if saldo >= prezzo:
    await pool.execute("UPDATE profili SET coin = coin - $2 WHERE user_id=$1", uid, prezzo)
    await consegna_oggetto(uid)
```

```python
# GIUSTO: una sola istruzione che controlla e scala; l'oggetto si consegna solo se ha scalato.
async with pool.acquire() as c, c.transaction():
    scalato = await c.fetchval(
        "UPDATE profili SET coin = coin - $2 WHERE user_id = $1 AND coin >= $2 RETURNING coin", uid, prezzo
    )
    if scalato is None:
        raise SaldoInsufficiente()
    await consegna_oggetto(c, uid)          # nella stessa transazione
```

Lo stesso vale per: premi riscattati una volta sola (vincolo unico +
`ON CONFLICT DO NOTHING ... RETURNING`), giveaway, scambi tra utenti (blocca le
due righe **sempre nello stesso ordine**: prima l'ID più piccolo, o va in stallo),
XP guadagnati da più eventi insieme.

## E8. SQL costruito con il testo

```python
# SBAGLIATO
await pool.fetch(f"SELECT * FROM tag WHERE guild_id={gid} AND nome='{nome}'")
await pool.execute(f"UPDATE impostazioni SET {campo} = $1", valore)     # `campo` scelto dall'utente
assert campo in CAMPI                                                   # sparisce con `python -O`
```

```python
# GIUSTO
await pool.fetch("SELECT * FROM tag WHERE guild_id = $1 AND nome = $2", gid, nome)
if campo not in CAMPI_AMMESSI:            # elenco fisso nel codice
    raise ValueError(f"campo sconosciuto: {campo}")
await pool.execute(f"UPDATE impostazioni SET {campo} = $1 WHERE guild_id = $2", valore, gid)
```

Ricerche con `LIKE`: i caratteri `%` e `_` dell'utente vanno resi innocui
(`.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")`) e la query ha un `LIMIT`.

## E9. L'URL scelto dall'utente

```python
# SBAGLIATO: http://169.254.169.254/…, http://127.0.0.1:8422/…, un redirect verso la rete interna.
async with aiohttp.ClientSession() as s:
    async with s.get(url_utente) as r:
        dati = await r.read()               # senza tetto: un file da 10 GB
```

```python
# GIUSTO
from core.safe_http import safe_get, url_e_sicuro
if not await url_e_sicuro(url_utente):
    return await rispondi("Questo indirizzo non è ammesso.")
risposta = await safe_get(url_utente, max_bytes=2_000_000)
```

Mai dare l'URL a un altro programma (Lavalink, ffmpeg, un servizio AI) senza
`url_e_sicuro`. I link Deezer non vanno mai a Lavalink (D73).

## E10. Il processo esterno

Caso vero (#166): la sandbox restava appesa per sempre dopo aver ucciso il figlio.

```python
# SBAGLIATO
subprocess.run(f"ffmpeg -i {percorso} uscita.mp4", shell=True)     # il nome del file diventa un comando
proc.kill(); await proc.wait()      # tubo pieno di dati non letti: wait() non torna più
```

```python
# GIUSTO: lista di argomenti, formato esplicito, tempo massimo, ambiente ridotto, tubo svuotato.
subprocess.run(
    [ffmpeg, "-nostdin", "-protocol_whitelist", "file,pipe", "-f", formato_dai_byte, "-i", str(percorso), ...],
    stdin=subprocess.DEVNULL, timeout=secondi, env={"PATH": os.environ.get("PATH", "")}, check=False,
)
uccidi()
await asyncio.wait_for(svuota_e_attendi(), ATTESA_CHIUSURA)
```

## E11. Il segreto che finisce dove non deve

```python
# SBAGLIATO
logger.info("Chiamo %s", url_con_token)                    # ?key=… nei log
await interaction.followup.send(f"Errore: {exc}")           # l'eccezione può contenere URL, percorsi, SQL
if token_inviato == token_vero: ...                        # confronto che lascia misurare il tempo
await pool.execute("INSERT INTO sessioni (token) VALUES ($1)", token)   # chi legge la tabella entra
```

```python
# GIUSTO
logger.info("Chiamo %s", _per_log(url))                    # senza query
logger.exception("Errore nel comando X"); await interaction.followup.send(await testo_per(interaction, "errore_generico"))
if hmac.compare_digest(token_inviato, token_vero): ...
await pool.execute("INSERT INTO sessioni (impronta) VALUES ($1)", hashlib.sha256(token.encode()).hexdigest())
```

## E12. Il guadagno infinito e il costo infinito

```python
# SBAGLIATO: XP a ogni messaggio (anche del bot, anche ripetuto), AI a ogni richiesta, nessun tetto.
await dai_xp(message.author.id, 10)
risposta = await chiedi_ai(testo)
```

```python
# GIUSTO
if message.author.bot or message.webhook_id:        # niente bot, niente webhook
    return
if not pausa_xp.consenti(message.author.id):        # una volta al minuto per utente
    return
if not await tetto_giornaliero_ai(guild_id).consenti():   # tetto per server
    return await rispondi("Limite di oggi raggiunto.")
```

**Come ragionare:** «Se un utente lo fa mille volte al secondo con dieci account,
cosa si riempie? Cosa costa? Cosa si rompe per gli altri server?» Ogni cache e
ogni coda ha un massimo; a coda piena si rifiuta, non si accumula.

## E13. Il pannello web

```python
# SBAGLIATO
return web.Response(text=f"<h1>Ciao {nome}</h1>", content_type="text/html")   # XSS
gid = int(request.query["guild"]); await salva(gid, dati)                    # nessun controllo: chiunque sia loggato scrive ovunque
```

```python
# GIUSTO: modello Jinja con escape automatico; il server della richiesta si controlla ogni volta.
guild = await ponte.server_gestibile(bot, guild_id, utente_id)   # il bot c'è E l'utente può gestirlo ADESSO
if guild is None:
    return _errore(request, 403, ...)
if not regole.csrf_valido(chiave, token_sessione, form.get("csrf")):
    return _errore(request, 403, ...)
```

## E14. Modelli e segnaposto scritti dagli utenti

```python
# SBAGLIATO: "{utente.__class__.__init__.__globals__}" legge tutto il programma.
messaggio = modello_utente.format(utente=membro, server=guild)
```

```python
# GIUSTO: solo segnaposto di un elenco chiuso, sostituiti con testi già puliti.
SEGNAPOSTO = {"{utente}": membro.display_name, "{server}": guild.name, "{conta}": str(guild.member_count)}
for chiave, valore in SEGNAPOSTO.items():
    testo = testo.replace(chiave, pulisci(valore))
```

---

# Metodo: come si cerca una falla in un diff

1. **Segui il dato.** Parti da ogni punto in cui entra qualcosa di non fidato
   (opzione di un comando, `message.content`, `attachment`, `custom_id`,
   `request.query`, riga del database scritta da un utente) e seguilo fino a
   dove **agisce** (SQL, file, rete, messaggio, ruolo, processo). Su quel
   percorso deve esserci un controllo. Se non lo trovi, è una falla.
2. **Cambia attore.** Rileggi il codice come: utente senza permessi; moderatore
   che vuole diventare admin; admin di un server che vuole toccare un altro
   server; bot o webhook; la stessa persona con due finestre aperte.
3. **Cambia misura.** Zero, uno, il massimo, il massimo più uno, un milione;
   stringa vuota, 4.000 caratteri, solo emoji, solo caratteri invisibili.
4. **Cambia tempo.** Due volte insieme; a metà di un riavvio; dopo che il
   membro è uscito; dopo che il canale o il ruolo è stato cancellato; un bottone
   premuto dopo mesi.
5. **Togli un pezzo.** Database giù, sandbox giù, Discord che risponde 429 o
   500, servizio esterno lento. Il codice deve **chiudere** (non fare), non aprire.
6. **Guarda cosa esce.** Log, messaggi d'errore, embed, file, intestazioni HTTP:
   c'è un segreto, un percorso, un ID di un altro server, un testo non pulito?
7. **Scrivi il test che lo dimostra.** Un difetto senza test torna.
