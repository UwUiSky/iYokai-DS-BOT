# VPN e proxy nella verifica web (D64, D65, D67)

Chi si verifica dalla pagina web da una VPN, un proxy, Tor o una rete di data center viene bloccato subito.
Nessun metodo è perfetto: proxy residenziali e alcune VPN private passano; reti aziendali, reti mobili
condivise e iCloud Private Relay possono sembrare proxy. Per questo gli admin hanno il bottone «Lascia passare»
e ogni server può spegnere la regola (`verify_blocca_vpn`, di base acceso).

## Gli strati (in ordine)
| Strato | Metodo | Dati | Forte o debole |
|---|---|---|---|
| ASN di hosting e data center | `asn` | banca dati ASN `GEOIP_ASN_MMDB` + `data/vpn/asn_hosting.txt` | forte |
| Nodi di uscita Tor | `tor` | `data/vpn/tor_uscita.txt` | forte |
| Reti di VPN e data center | `elenco` | `data/vpn/reti_vpn.txt`, `reti_datacenter.txt` (IPv4 e IPv6) | forte |
| Intestazioni di proxy mandate dal client | `intestazioni` (X-Forwarded-For, Forwarded), `via` (Via) | la richiesta; contano solo se arriva da un IP pubblico che non è un proxy fidato (`WEB_PANEL_TRUSTED_PROXY`) | forte / debole (Via) |
| Fuso orario del browser diverso dal paese dell'IP | `fuso` | `data/vpn/fuso_paesi.txt` + `GEOIP_PAESI_MMDB` | debole |
| Servizio esterno (facoltativo) | `servizio` | proxycheck.io, solo con `VPN_PROXYCHECK_KEY` | forte |

Un segnale forte blocca; i deboli bloccano solo in due insieme. IP privati, locali, riservati e CGNAT non si
bloccano mai. Il servizio esterno si chiama solo se nessuno strato locale ha già deciso, con cache per impronta
dell'IP (un'ora) e tetto giornaliero (`VPN_SERVIZIO_TETTO`, base 900; il livello gratuito dà 1.000 richieste al
giorno). Timeout, errore o tetto finito: la verifica prosegue senza il servizio. Un reverse proxy locale non
dichiarato tra i fidati non fa scattare le intestazioni (altrimenti bloccherebbe tutti).

Grandi reti bloccate di base dall'elenco ASN (data center, non accessi di casa): Google (AS15169), Amazon
(AS16509, AS14618), Microsoft (AS8075), Hetzner (AS24940), OVH (AS16276), DigitalOcean (AS14061), Linode
(AS63949), Vultr (AS20473), Alibaba (AS45102). Chi esce da queste reti per motivi veri (desktop remoto,
browser in cloud, alcune reti aziendali) si sblocca con «Lascia passare».

## Come aggiornare
- `python3 scripts/aggiorna_geoip.py` (mensile): paesi e ASN di DB-IP in `data/geoip/`; metti i percorsi in `GEOIP_PAESI_MMDB` e `GEOIP_ASN_MMDB`.
- `python3 scripts/aggiorna_vpn.py` (settimanale): ASN, Tor e reti in `data/vpn/`. Il bot rilegge i file entro un minuto. Un file scaricato rotto o troppo piccolo non sostituisce quello buono. Le reti più larghe di /8 (IPv4) o /16 (IPv6) negli elenchi si ignorano: sarebbero un errore della fonte.
- `python3 scripts/aggiorna_vpn.py --fusi`: rigenera `fuso_paesi.txt` dal database dei fusi di sistema.
`asn_hosting.txt` e `fuso_paesi.txt` sono nel repository; gli altri elenchi sono generati (gitignore).

## Fonti e licenze
| Dato | Fonte | Licenza |
|---|---|---|
| Banca dati ASN e paesi | DB-IP.com «IP to ASN Lite» e «IP to Country Lite» | CC BY 4.0 (attribuzione: «Dati di DB-IP.com») |
| ASN di hosting | github.com/brianhama/bad-asn-list (`bad-asn-list.csv`) | MIT |
| Reti VPN e data center | github.com/X4BNet/lists_vpn (`output/vpn`, `output/datacenter`, IPv4 e IPv6) | MIT |
| Nodi di uscita Tor | check.torproject.org/torbulkexitlist (elenco ufficiale pubblico del Tor Project) | elenco pubblico; il sito del Tor Project è CC BY 3.0 US: da confermare se si ridistribuisce |
| Fusi orari | database IANA (`zone.tab`) | pubblico dominio |
| Servizio esterno | proxycheck.io, piano gratuito (1.000 richieste/giorno con chiave) | termini del servizio: l'owner li legge prima di mettere la chiave (uso commerciale non chiarito dalla pagina dei prezzi) |

## Privacy
Tabelle (tutte nel registro dei dati, `/utility privacy cancella` le toglie): `verify_vpn` (esito, metodo, data; 30 giorni),
`verify_blocchi` (ultimo blocco, server e motivo; 1 giorno), `verify_vpn_storico` (server, metodo, data, founder e admin dei
«Lascia passare»; 180 giorni), `verify_ip` (vedi sotto). Il servizio esterno riceve l'IP: è scritto nell'informativa.
Gli admin vedono solo il **numero** dei server che hanno già accettato la persona; i nomi solo dei server con
`verify_condividi_nome` acceso; il proprietario del bot vede sempre i nomi con `/owner system storico-vpn` e nella
pagina del proprietario del pannello (`/proprietario/storico-vpn`).

## Soglia dello storico condiviso (D67)
Il «Lascia passare» vale negli altri server solo con **almeno 3 approvazioni** di server diversi, a **un'ora di distanza**
una dall'altra, da server con **founder (owner del server) diversi** e da **admin diversi** (chi ha premuto il bottone).
Basta un gruppo di 3 righe tutte diverse fra loro (`core/verify_vpn_logic.py::storico_basta`). Sotto la soglia vale
solo nel server che l'ha dato. Le righe di prima della regola (senza founder/admin) non contano. Casi provati:
stesso founder in 3 server, stesso admin in 3 server, 3 clic nella stessa ora, solo 2 approvazioni.

## IP cifrati, solo per il proprietario (D67)
- Ogni verifica web con IP pubblico salva l'IP in `verify_ip` (migrazione 0530), **cifrato** con AES-256-GCM
  (`core/oauth_crypto.py`, chiave `VERIFY_IP_ENCRYPTION_KEY` nel `.env`, diversa da `OAUTH_ENCRYPTION_KEY`) e legato
  a server e persona (dato associato). Senza chiave **non si salva niente**. Una riga per IP (impronta HMAC), al
  massimo 20 per persona. Non cambiare la chiave: gli IP già salvati diventano «(illeggibile)».
- Lo vede **solo il proprietario**: `/owner system storico-vpn` e `/proprietario/storico-vpn`. Mai agli admin, mai nei log
  (se il salvataggio fallisce si logga solo il tipo dell'errore, senza traceback).
- Scadenza (`scade_il`, pulita dal lavoro giornaliero): persona esce dal server = 30 giorni (rientra: torna senza
  scadenza); bot tolto dal server = 30 giorni su tutte le righe (se rientra, ogni riga riprende la scadenza del suo
  motivo); **kick** = 180 giorni; **ban** = nessuna scadenza finché è attivo, 30 giorni dopo lo sblocco; tetto assoluto
  365 giorni dall'ultimo uso. L'espulsione si riconosce dal registro di Discord (serve il permesso «Vedi il registro
  azioni»; senza, l'uscita conta come volontaria e si cancella prima).
- `/utility privacy cancella` cancella gli IP, **tranne** quelli con motivo ban o kick (interesse legittimo di sicurezza):
  la richiesta di chi è bannato o espulso si valuta a mano. Tetti scelti da chi sviluppa (D67), da confermare all'owner.

## Blocchi e ticket (D65, D67)
Ogni blocco della verifica, web o su Discord (VPN, paese in attesa, captcha sbagliato o scaduto, controlli del server, reazione) invita la persona a scrivere in privato al bot,
se il ModMail del server è pronto. Il primo messaggio apre il ticket con lo staff di quel server e il motivo allegato.
