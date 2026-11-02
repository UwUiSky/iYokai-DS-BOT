# Sandbox delle immagini (D61, D62)

Il filtro immagini sospette non apre mai un allegato nel processo del bot. I byte vanno in una
cartella di quarantena e un processo separato, nuovo per ogni immagine, li analizza con limiti di
memoria (512 MiB), di CPU (4 s) e di tempo vero (8 s). Ci sono due modi.

- **Modo A, consigliato:** servizio di sistema `iyokai-sandbox`. Utente senza permessi, niente rete,
  quarantena in sola lettura.
- **Modo B, ripiego:** il bot avvia da sé lo stesso processo con gli stessi limiti e prova `unshare -rn`
  per togliere la rete. Il log del bot scrive una volta «sandbox ridotta». Il filtro funziona, ma senza
  l'isolamento del sistema.

## Installazione del modo A (una volta, da root)

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

Il bot scrive i file in quarantena (utente `iyokai`, file `0640`); il servizio li legge dal gruppo
`iyokai-sbx`. Il socket è `/run/iyokai-sbx/sock` (`0660`, gruppo `iyokai-sbx`): per questo il bot entra nel
gruppo `iyokai-sbx` (`usermod`, poi riavvio del bot). Il servizio invece non entra mai nel gruppo del bot e non
vede `.env` né `logs/`: un worker compromesso non può leggere i segreti del bot. Per usare altri percorsi: variabili `IYOKAI_QUARANTENA_DIR` (bot e servizio) e
`IYOKAI_SANDBOX_SOCKET` (bot e servizio).

`ExecStart` deve usare lo stesso interprete del bot (di solito quello del suo ambiente virtuale): con un
Python senza Pillow il servizio risponde «sandbox non disponibile» e le immagini restano non analizzate.

L'unità non usa `MemoryDenyWriteExecute`: provalo sul server e accendilo se Pillow e zxing-cpp
continuano a funzionare.

## Cosa resta sul disco

Un'immagine pulita si cancella subito dopo l'analisi. Un'immagine sospetta o malevola resta 72 ore,
poi la pulizia (ogni 15 minuti) la toglie. Il registro è la tabella `quarantena_file` (senza dati
dell'autore). Nei log non va mai il file originale.

## Coda piena o servizio fermo

I controlli sui byte e la libreria delle impronte girano sempre. Se il resto non può girare, il
messaggio resta e il log scrive «immagine non analizzata»; fa eccezione un account con meno di 7 giorni
(o nel server da meno di 1 giorno): il messaggio si toglie e l'autore riceve «riprova fra poco».
L'owner riceve al massimo un avviso ogni 10 minuti.

## Aggiornamenti

Pillow e zxing-cpp (versione fissa in `requirements.txt`) si aggiornano subito alle patch di sicurezza.
