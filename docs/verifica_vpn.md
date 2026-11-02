# VPN e proxy nella verifica web (D64, D65)

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

## Come aggiornare
- `python3 scripts/aggiorna_geoip.py` (mensile): paesi e ASN di DB-IP in `data/geoip/`; metti i percorsi in `GEOIP_PAESI_MMDB` e `GEOIP_ASN_MMDB`.
- `python3 scripts/aggiorna_vpn.py` (settimanale): ASN, Tor e reti in `data/vpn/`. Il bot rilegge i file entro un minuto. Un file scaricato rotto o troppo piccolo non sostituisce quello buono.
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
L'IP si usa solo in quel momento e non si salva. Tabelle (tutte nel registro dei dati, `/privacy cancella` le toglie):
`verify_vpn` (esito, metodo, data; 30 giorni), `verify_blocchi` (ultimo blocco, server e motivo; 1 giorno),
`verify_vpn_storico` (server, metodo, data dei «Lascia passare»; 180 giorni). Il servizio esterno riceve l'IP: è scritto
nell'informativa. Gli admin vedono solo il **numero** dei server che hanno già accettato la persona; i nomi solo
dei server con `verify_condividi_nome` acceso; il proprietario del bot vede sempre i nomi con
`/owner system storico-vpn`.

## Blocchi e ticket (D65)
Ogni blocco della verifica web (VPN, paese in attesa, controlli del server) invita la persona a scrivere in privato al bot,
se il ModMail del server è pronto. Il primo messaggio apre il ticket con lo staff di quel server e il motivo allegato.
