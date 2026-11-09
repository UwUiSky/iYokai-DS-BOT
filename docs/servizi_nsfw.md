# Servizi per adulti (solo bot NSFW)

Controllo del 09/11/2026 (D70, #131). «Stato»: *verificato* = letto su pagina ufficiale; *parziale* = letto in parte; *non verificato* = dato da conoscenza generale o da fonti non ufficiali (la sentinella lo ricontrolla). Uso: copia `config/nsfw_fornitori.env.example` in `config/nsfw_fornitori.env` (fuori dal repository), incolla le chiavi, riavvia.

## Regola fissa (D70)

Queste fonti sono usate solo dal bot NSFW e solo nei canali con limite d'età. Non entrano nell'elenco delle GIF normali. Tutte spente di base.

L'elenco `data/nsfw/tag_vietati.txt` esclude **sempre**:
- ogni contenuto con minori o che li richiami, in tutte le lingue (loli, shota, child e simili);
- il gore estremo;
- il non consensuale (e la zoofilia, vietata dalla legge italiana).

Una ricerca con un tag vietato non parte. Un risultato con un tag vietato (tag, titolo, descrizione) si scarta. Nessun interruttore lo spegne. È un obbligo di legge (in Italia anche la pornografia «virtuale» con minori è reato) e delle regole di Discord. Il primo elenco va ampliato, mai accorciato senza decisione dell'owner.

| Servizio | Acceso | URL base | Endpoint / ricerca per tag | Chiave | Limiti | Termini | Note NSFW | Stato | Fonte |
|---|---|---|---|---|---|---|---|---|---|
| Rule34.xxx | no | https://api.rule34.xxx | GET /index.php?page=dapi&s=post&q=index&json=1&tags={tag}+{tag}&limit=&pid= | probabile: user_id + api_key dal profilo (da verificare: fonti non ufficiali) | limite per pagina circa 1000; frequenza non letta | non letti: la pagina di aiuto non è raggiungibile | Solo adulti. Ricerca per tag con «-tag» per escludere. Contiene materiale vietato dall'elenco: filtrare SEMPRE tag cercati e tag dei risultati | non verificato: dati da conoscenza generale o fonti non ufficiali, pagina ufficiale non letta il 09/11/2026; da ricontrollare | https://rule34.xxx/index.php?page=help&topic=dapi |
| Gelbooru | no | https://gelbooru.com | GET /index.php?page=dapi&s=post&q=index&json=1&tags=&limit= | probabile (api_key + user_id) | non letti | non letti | Ratings: explicit, questionable, sensitive, general. Filtrare sempre l'elenco vietato | non verificato: dati da conoscenza generale o fonti non ufficiali, pagina ufficiale non letta il 09/11/2026; da ricontrollare | https://gelbooru.com/index.php?page=wiki&s=view&id=18780 |
| Danbooru | no | https://danbooru.donmai.us | GET /posts.json?tags=rating:e+{tag}&limit= (utenti gratuiti: massimo 2 tag) | no per letture di base; con login e chiave limiti più alti | circa 10 richieste al secondo per le letture (non letto) | non letti; contiene molto materiale vietato (tag con minori): filtro obbligatorio | Rating: g, s, q, e | non verificato: dati da conoscenza generale o fonti non ufficiali, pagina ufficiale non letta il 09/11/2026; da ricontrollare | https://danbooru.donmai.us/wiki_pages/help:api |
| e621 (furry) | no | https://e621.net | GET /posts.json?tags=&limit= (User-Agent con nome del bot obbligatorio) | no (login per tag nascosti) | 1 richiesta al secondo (non letto) | non letti; contiene materiale vietato (tag «cub» ecc.): filtro obbligatorio | Rating: s, q, e | non verificato: dati da conoscenza generale o fonti non ufficiali, pagina ufficiale non letta il 09/11/2026; da ricontrollare | https://e621.net/wiki_pages/2425 |
| waifu.pics (parte NSFW) | no | https://api.waifu.pics | GET /nsfw/{categoria} (waifu, neko, trap, blowjob) | no | non verificato | come waifu.pics SFW | Solo adulti. Nessuna ricerca per tag: si scelgono categorie. Escludere «trap» | non verificato: dati da conoscenza generale o fonti non ufficiali, pagina ufficiale non letta il 09/11/2026; da ricontrollare | https://waifu.pics/docs |
| purrbot.site (parte NSFW) | no | https://api.purrbot.site/v2 | GET /img/nsfw/{categoria}/gif · GET /list/nsfw/{percorso} | no | non indicati | come purrbot SFW (https://purrbot.site/legal/api) | Solo adulti. Categorie lette: anal, blowjob, cum, fuck, yaoi, yuri, threesome. Nessuna ricerca per tag | parziale 09/11/2026 (pagina ufficiale letta solo in parte) | https://purrbot.site/api |
| waifu.im (parte NSFW) | no | https://api.waifu.im | GET /search?is_nsfw=true&included_tags= | da verificare | non verificati | non verificati (docs bloccate ai robot) | Solo adulti. Ricerca per tag; filtro vietati obbligatorio sui tag restituiti | non verificato: dati da conoscenza generale o fonti non ufficiali, pagina ufficiale non letta il 09/11/2026; da ricontrollare | https://docs.waifu.im/ |
| nekos.life (parte NSFW) | no | https://nekos.life/api/v2 | GET /img/{categoria} per le categorie adulte (lewd, gasm, spank… non confermate come adulte) | da verificare | non verificati | non verificati | Solo adulti. Funzionamento non confermato | parziale 09/11/2026 (solo elenco rotte) | https://nekos.life/api/v2/endpoints |
