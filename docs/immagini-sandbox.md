# Sandbox obbligatoria per i file degli utenti (D61, D62, D74, blocco B)

**Ogni file caricato da un utente** (immagini, avatar, sfondi, allegati dei log, PDF, audio, video, testo) si apre
solo in un processo separato e blindato: il servizio di sistema `iyokai-sandbox`. Il processo del bot non apre mai
quei byte e non importa nessun decoder (Pillow in lettura, pillow-heif, pypdf, ffmpeg): un test (`tests/test_sandbox_obbligatoria.py`)
fallisce se qualcuno lo fa. Per ogni lavoro il servizio avvia un processo figlio nuovo, con limiti di memoria, di CPU e
di tempo vero, senza file scrivibili (tranne una cartella temporanea privata per le conversioni) e senza rete.

**Niente ripiego.** Se il servizio non risponde, o se il suo processo ha una rete (manca `PrivateNetwork=yes`), il lavoro
si rifiuta: l'utente legge «Il controllo sicuro dei file non è disponibile in questo momento», il log del bot scrive
«Sandbox: servizio iyokai-sandbox non raggiungibile» e le immagini dei filtri restano «non analizzate» (messaggio tolto
solo per gli account nuovi, vedi sotto). Non esiste più un «modo B» con lo stesso utente del bot.

Cosa passa dalla sandbox:

- **Filtro immagini e copie degli allegati** (log, ticket, ModMail, backup): `core/immagini_pipeline.py` scrive i byte in
  quarantena e chiede il lavoro al servizio.
- **Schede, filtri e immagini dei comandi** (rank card, benvenuto, meme, avatar, sfondi, moneta, foto delle auto,
  emoji e sticker, AI): `core/safe_image.apri_in_sandbox` manda i byte al servizio, che li decodifica, li riduce e rende
  i soli pixel grezzi; il bot ricostruisce l'immagine con `Image.frombytes`, senza nessun decoder.
- **PDF, audio, video, testo**: conversioni del servizio (`core/conversioni_worker.py`).

## Cosa serve sul server

Debian 11+ o Ubuntu 22.04+, x86_64 o arm64 (`aarch64`). Pacchetti: `python3-venv`, `ffmpeg` (con `ffprobe`, libx264,
libopus, aac). Pillow, pillow-heif, pypdf e zxing-cpp hanno ruote per entrambe le architetture (`pip install -r requirements.txt`).
Il servizio usa lo stesso ambiente virtuale del bot. `ProtectProc` e `ProtectKernelLogs` richiedono systemd 247+: su
sistemi più vecchi sono ignorati con un avviso nel journal, il resto dell'isolamento vale lo stesso.

## Installazione (una volta, da root)

Percorsi d'esempio: il bot gira come utente `iyokai` e sta in `/opt/iyokai`. Adatta i nomi.

```
useradd --system --no-create-home --shell /usr/sbin/nologin iyokai-sbx
usermod -aG iyokai-sbx iyokai
install -d -o iyokai -g iyokai-sbx -m 2750 /var/lib/iyokai/quarantena
cp deploy/systemd/iyokai-sandbox.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now iyokai-sandbox
systemctl status iyokai-sandbox
```

Prova dopo l'installazione:

```
journalctl -u iyokai-sandbox -n 20          # «in ascolto su /run/iyokai-sbx/sock», nessun «ha una rete»
systemd-analyze security iyokai-sandbox     # punteggio dell'isolamento (più basso = meglio)
sudo -u iyokai test -S /run/iyokai-sbx/sock && echo "il bot raggiunge il socket"
```

Se nel journal compare «il processo ha una rete, ogni lavoro sarà rifiutato», l'unità non ha `PrivateNetwork=yes`:
rimetti il file di `deploy/systemd/` e fai `systemctl daemon-reload && systemctl restart iyokai-sandbox`.

Il bot scrive i file in quarantena (utente `iyokai`, file `0640`); il servizio li legge dal gruppo
`iyokai-sbx`. Il socket è `/run/iyokai-sbx/sock` (`0660`, gruppo `iyokai-sbx`): per questo il bot entra nel
gruppo `iyokai-sbx` (`usermod`, poi riavvio del bot). Il servizio invece non entra mai nel gruppo del bot e non
vede `.env` né `logs/`: un worker compromesso non può leggere i segreti del bot. Per usare altri percorsi: variabili `IYOKAI_QUARANTENA_DIR` (bot e servizio) e
`IYOKAI_SANDBOX_SOCKET` (bot e servizio).

`ExecStart` deve usare lo stesso interprete del bot (di solito quello del suo ambiente virtuale): con un
Python senza Pillow il servizio risponde «sandbox non disponibile» e le immagini restano non analizzate.

L'unità non usa `MemoryDenyWriteExecute`: provalo sul server e accendilo se Pillow e zxing-cpp
continuano a funzionare.

## Conversioni di PDF, audio, video e testo (D74)

Lo stesso servizio converte anche gli altri allegati, sempre in un processo nuovo per file
(`core/conversioni_worker.py`), senza rete, con tetti di memoria, CPU e tempo vero, uscita al massimo di 10 MiB e
scrittura solo in una cartella temporanea privata che il servizio toglie a ogni lavoro. Senza
servizio l'allegato resta una scheda.

- **Serve `ffmpeg`** (con `ffprobe`, `libx264`, `libopus`, `aac`): `apt install ffmpeg`. Il servizio non ha rete:
  ffmpeg parte con `-protocol_whitelist file,pipe` e con il formato in entrata scelto dai byte.
- PDF: ricostruito con `pypdf` (20 MiB in entrata, 200 pagine). Audio: Opus in Ogg, al massimo 10 minuti.
  Video: H.264 + AAC in MP4, al massimo 2 minuti e 720p, solo per ticket, ModMail e backup. Testo: UTF-8 in `.txt`,
  256 KiB. Tempi veri massimi: testo 5 s, PDF 25 s, audio 45 s, video 120 s. File in uscita sotto 9,5 MiB.
- Per ogni server c'è un tetto di tempo-sandbox al giorno (impostazione `sandbox_secondi_giorno`, di base 600
  secondi, 0 = nessuna conversione): oltre, resta la scheda.
- Il video da 2 minuti a 720p può richiedere fino a 2 minuti di una CPU: se i video vengono scartati per il
  tempo, il servizio ha troppo poca CPU (`CPUQuota` nell'unità).
- Dopo l'aggiornamento: `systemctl daemon-reload && systemctl restart iyokai-sandbox`, poi guarda
  `journalctl -u iyokai-sandbox` (un filtro di chiamate di sistema troppo stretto per ffmpeg si vede lì).

## Cosa resta sul disco

Un'immagine pulita si cancella subito dopo l'analisi. Un'immagine sospetta o malevola resta 72 ore,
poi la pulizia (ogni 15 minuti) la toglie. Il registro è la tabella `quarantena_file` (senza dati
dell'autore). Nei log non va mai il file originale.

## Coda piena o servizio fermo

I controlli sui byte e la libreria delle impronte girano sempre. Se il resto non può girare, il
messaggio resta e il log scrive «immagine non analizzata»; fa eccezione un account con meno di 7 giorni
(o nel server da meno di 1 giorno): il messaggio si toglie e l'autore riceve «riprova fra poco».
L'owner riceve al massimo un avviso ogni 10 minuti.

## Download degli allegati dei log

Prima di scaricare un allegato per il log (`core/allegati_cancello.py`) il bot controlla che ci sia posto: al massimo
4 download insieme, 16 in attesa, 48 MiB di byte dichiarati in volo e la coda della sandbox sotto 50 lavori su 100.
Sopra soglia l'allegato non si scarica: nel log resta la scheda (nome, tipo, peso) senza byte e senza anteprima.

## Aggiornamenti

Pillow, pillow-heif, pypdf, zxing-cpp (versioni fisse in `requirements.txt`) e `ffmpeg` di sistema si aggiornano subito alle
patch di sicurezza.
