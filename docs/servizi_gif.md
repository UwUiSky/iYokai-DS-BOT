# Servizi GIF di reazione e azione

Controllo del 09/11/2026 (D70, #131). «Stato»: *verificato* = letto su pagina ufficiale; *parziale* = letto in parte; *non verificato* = dato da conoscenza generale o da fonti non ufficiali (la sentinella lo ricontrolla). Uso: copia `config/gif_fornitori.env.example` in `config/gif_fornitori.env` (fuori dal repository), incolla le chiavi, riavvia.

Le GIF di reazione e azione sono gratuite per tutti (D70). Solo fonti SFW; le fonti per adulti sono in `docs/servizi_nsfw.md`. Le fonti miste (waifu.pics, purrbot.site, waifu.im, nekos.life) qui si usano solo con le categorie SFW.

| Servizio | Acceso | URL base | Endpoint | Chiave | Limiti | Termini | NSFW | Attribuzione | Stato | Fonte |
|---|---|---|---|---|---|---|---|---|---|---|
| nekos.best | si | https://nekos.best/api/v2 | GET /{categoria}?amount=1-20 · GET /search?query=&type=2&category= · GET /endpoints (elenco vivo) | no (User-Agent ben formato obbligatorio) | limiti non pubblicati nelle pagine lette; limiti, filtro del traffico e ban IP previsti dai termini | VIETATO l'uso commerciale; vietati scraping e download in massa; cache solo privata; vietato addestrare modelli. Rischio «bot con abbonamenti» deciso dall'owner (D70) | Solo SFW (esclusi anche vestiti suggestivi): nessun filtro da impostare | Obbligo di non togliere i crediti: anime_name, artist_name, artist_href, source_url (header/JSON) | verificato 09/11/2026 su pagina ufficiale | https://docs.nekos.best/getting-started/api-endpoints · https://docs.nekos.best/legal/tos · https://docs.nekos.best/getting-started/faq |
| waifu.pics | si | https://api.waifu.pics | GET /sfw/{categoria} · GET /endpoints (elenco) | no | non verificato (di solito circa 1 richiesta al secondo per IP) | non letti: la pagina docs è bloccata ai robot (robots_disallowed) | Misto: usare SOLO /sfw/…; le categorie /nsfw/… stanno in config/nsfw_fornitori.env.example | non letta | non verificato: pagina ufficiale non leggibile; non verificato: dati da conoscenza generale o fonti non ufficiali, pagina ufficiale non letta il 09/11/2026; da ricontrollare | https://waifu.pics/docs |
| otakugifs | si | https://api.otakugifs.xyz | GET /gif?reaction={nome}&format=gif · GET /gif/allreactions (elenco) | no | non verificato | non verificati: il sito è una pagina JavaScript, nessun testo letto | Presunto solo SFW, da verificare con /gif/allreactions | non letta | non verificato: dati da conoscenza generale o fonti non ufficiali, pagina ufficiale non letta il 09/11/2026; da ricontrollare | https://otakugifs.xyz/ |
| purrbot.site | si | https://api.purrbot.site/v2 | GET /img/sfw/{categoria}/gif (anche /img/sfw/{categoria}/img) · GET /list/sfw/{percorso} (elenco; il percorso va preso dalla documentazione) | no | non indicati nelle pagine lette | Termini su https://purrbot.site/legal/api: pensata per progetti Discord; nessun divieto di uso commerciale e nessun limite scritto nella pagina; licenza MIT; contatto support@purrbot.site | Misto: usare SOLO /img/sfw/…; /img/nsfw/… sta in config/nsfw_fornitori.env.example | Non richiesta dalla pagina dei termini | parziale 09/11/2026 (pagina ufficiale letta solo in parte) | https://purrbot.site/api · https://purrbot.site/legal/api |
| waifu.im | no | https://api.waifu.im | GET /search (parametri: included_tags, is_nsfw=false …) · elenco tag su /tags | da verificare (versioni recenti possono chiedere un token) | non verificati | non verificati: le pagine docs sono bloccate ai robot | Misto: nelle GIF normali SEMPRE is_nsfw=false; il resto nel file NSFW | da verificare | non verificato: dati da conoscenza generale o fonti non ufficiali, pagina ufficiale non letta il 09/11/2026; da ricontrollare | https://docs.waifu.im/ |
| nekos.life | no | https://nekos.life/api/v2 | GET /img/{categoria} | da verificare | non verificati | non verificati; le vecchie rotte /api/… sono segnate «deprecate» nella pagina | Misto: dalla pagina non si capisce quali categorie siano adulte; escludere sempre lewd, gasm, spank e simili. Quelle adulte stanno nel file NSFW | non letta | parziale 09/11/2026 (solo elenco delle rotte letto; funzionamento non confermato) | https://nekos.life/api/v2/endpoints |
| Giphy | no | https://api.giphy.com/v1 | GET /gifs/search?api_key=&q=&rating=g&limit= (q massimo 50 caratteri) · /gifs/random · /stickers/search | si | Chiave beta: 100 chiamate all'ora (limit massimo 50). Più chiamate: richiesta di chiave di produzione, a pagamento per chi la ottiene | La documentazione descrive la ricerca «dal lato client»: per un bot lato server serve il permesso scritto (testo in fondo a questo file). Una chiave per ogni piattaforma/sezione | Parametro rating: g, pg, pg-13, r. Per un bot con ricerca libera usare sempre rating=g | Obbligo «Powered By GIPHY» ben visibile dove si usa l'API | verificato 09/11/2026 su pagina ufficiale (developers.giphy.com/docs/api; i termini completi non sono stati letti) | https://developers.giphy.com/docs/api |
| Klipy | no | https://api.klipy.com (da verificare nella documentazione) | GIF, sticker, clip, meme: pagine «Search API» in docs.klipy.com; chiave creata dal sito | si (chiave API) | non letti | Le pagine «API Usage & Attribution Guidelines» e «Integration Requirements» esistono ma il testo non è stato letto: permesso scritto richiesto da D70 (testo in fondo a questo file) | Esiste la sezione «Content filtering»: da leggere; usare il filtro più severo | Pagina «Attribution Guidelines» da leggere | non verificato: documentazione letta solo nell'indice | https://docs.klipy.com/ |
| Tenor (Google) | no | https://tenor.googleapis.com/v2 | (chiuso) | si | API chiusa il 30/06/2026 | Chiusa: non usare. Klipy è il sostituto più citato | — | — | parziale: confermata da giornali (9to5google 30/06/2026, PC Gamer, Shacknews, Gigazine); pagina ufficiale Google non letta | https://9to5google.com/2026/06/30/google-tenor-api-gif-updates/ |

Tenor: confermata la chiusura al 30/06/2026 (fonte giornalistica, vedi tabella).

## Testo per Giphy e Klipy (da inviare dall'owner)

Da inviare a Giphy (developers.giphy.com, form di richiesta chiave di produzione / support) e a Klipy (dal modulo di contatto o dal portale partner di klipy.com). Lo stesso testo, cambiando il nome.

```
Subject: Permission request - server-side GIF search for a free Discord bot

Hello GIPHY team,   (Hello KLIPY team,)

I develop "iYokai", a free multi-server Discord bot (Python, discord.py). Users run slash commands such as /hug or /slap and I would like to show a GIF from your catalog in the reply.

Because the bot runs on a server and not in the user's app, the search is made server-side. Your documentation describes client-side search, so I am asking for your written permission before using the API this way.

How I would use it:
- Search only with the safest rating (rating=g, or your strictest content filter). No adult content.
- Short search terms (the action name), results cached for a few minutes, no bulk download, no storage or redistribution of the files.
- Each reply shows the GIF link/embed together with the required attribution ("Powered By GIPHY" / KLIPY credit) and a link back to the source.
- The bot is free for everyone. GIFs are never part of any paid feature.
- Expected traffic is low (a few hundred requests per day). I will stay inside your rate limits and will use a production key if you ask for one.
- Users can report a GIF and I will remove it from the bot.

Could you confirm that this use is allowed, tell me which key type and limits apply, and tell me if you need any other attribution or technical requirement?

Thank you,
iYokai
```
