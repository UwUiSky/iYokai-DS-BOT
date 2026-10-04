# Catalogo — Vocali temporanei

Canali vocali creati al volo e gestiti da chi li apre. 21 voci. Bot
letti: VoiceMaster, TempVoice, Astro, Lawliet, MEE6. In quest'area i
concorrenti hanno poche funzioni in più di iYokai: per questo la
tabella è corta.

Legenda: ❌ manca · 🟡 parziale. "Scheda": NF-xx = scheda di
`NUOVE_FUNZIONI.md`; M x.y = riga di `MODIFICHE_ESISTENTE.md`;
"nuova" = non c'è ancora in nessun piano.

iYokai oggi (per confronto): canale generatore e categoria
(`/voicetemp-setup`), pannello con bottone per creare
(`/voicetemp-panel`), tetto di canali (`/voicetemp-cap`), ruoli
piattaforma PC/Console/Mobile, comandi del proprietario
`/voice rename|limit|lock|unlock|kick|transfer`, cancellazione a canale
vuoto.

| ID | Funzione o comando | Chi ce l'ha | iYokai oggi | Come farla in iYokai | Scheda |
|---|---|---|---|---|---|
| VOC-001 | Prendere la proprietà di un canale quando il proprietario è uscito | VoiceMaster (`/voice claim`) [VM] | ❌ manca | `/voice reclama`; vale solo se il proprietario non è nel canale | nuova |
| VOC-002 | Permettere l'ingresso a singoli utenti o ruoli in un canale chiuso | VoiceMaster (`/voice permit`) [VM], TempVoice (gestione dei permessi) [TV] | ❌ manca | `/voice permetti <utente o ruolo>`; permesso "Connetti" sul canale | nuova |
| VOC-003 | Vietare l'ingresso a singoli utenti o ruoli | VoiceMaster (`/voice reject`) [VM] | 🟡 parziale: `/voice kick` espelle ma l'utente può rientrare | `/voice vieta <utente>`; nega "Connetti" e scollega se presente | nuova |
| VOC-004 | Rendere il canale invisibile a chi non è dentro ("ghost") | VoiceMaster [VM] | ❌ manca | `/voice nascondi` e `/voice mostra`; permesso "Vedi canale" | nuova |
| VOC-005 | Cambiare la qualità audio (bitrate) del canale | VoiceMaster [VM] | ❌ manca | `/voice qualita`; massimo 96 kbps senza boost del server | nuova |
| VOC-006 | Canale di testo temporaneo affiancato al vocale | VoiceMaster ("Text") [VM] | 🟡 parziale: si usa la chat integrata del canale vocale | Basta la chat integrata; nessun lavoro, salvo richiesta | nuova |
| VOC-007 | Link d'invito al proprio canale da mandare a un utente | VoiceMaster ("Invite") [VM] | ❌ manca | `/voice invita <utente>`: DM con il link (invito a tempo, un solo uso); 1000 inviti per server | nuova |
| VOC-008 | Stato del canale ("cosa stiamo facendo") | VoiceMaster ("Status") [VM] | ❌ manca | `/voice stato <testo>`; usa lo stato dei canali vocali di Discord | nuova |
| VOC-009 | Menu nel canale con tutte le azioni, senza scrivere comandi | VoiceMaster ("Channel Interface", menu a tendina) [VM], TempVoice ("Interface Message") [TV], Astro (interfaccia pensata anche per il telefono) [ASTRO] | 🟡 parziale: alla creazione arriva un messaggio con i soli bottoni piattaforma, che muoiono dopo 5 minuti (LIM-26) | Vista persistente con rinomina, limite, blocca, nascondi, espelli, cedi; 5 bottoni per riga | M 7.6 |
| VOC-010 | Aspetto del menu personalizzabile dal server | Astro [ASTRO] | ❌ manca | Testo e colore dell'embed del menu; il resto nel pannello web | nuova |
| VOC-011 | Nome dei nuovi canali da un modello con variabili (nome utente, numero) | VoiceMaster (modo "Predefined": `{username}`, `{seq}`) [VM], Lawliet (`%VCName`, `%Index`, `%Creator`) [LAWLIET] | ❌ manca | Opzione `modello-nome` in `/admin voice`; nome ≤ 100 caratteri | nuova |
| VOC-012 | Canali numerati in sequenza (Stanza 1, Stanza 2…) | VoiceMaster (modo "Sequential") [VM] | ❌ manca | Variabile `{n}` del modello; riuso del primo numero libero | nuova |
| VOC-013 | Nuovo canale copiato da un canale modello (permessi, limite, qualità) | VoiceMaster (modo "Clone") [VM] | ❌ manca | `channel.clone()` del generatore; attenzione ai permessi ereditati | nuova |
| VOC-014 | Stanze già pronte prima che qualcuno entri: ce n'è sempre una vuota | VoiceMaster (modo "Dynamic") [VM] | ❌ manca | Tenere una stanza vuota di scorta per generatore; rispetta `/voicetemp-cap` | nuova |
| VOC-015 | I nuovi canali nascono chiusi (limite 1): li apre il creatore | Lawliet ("New Voice Channels Begin Locked") [LAWLIET] | ❌ manca | Opzione `nasce-chiuso: sì/no` | nuova |
| VOC-016 | Più canali generatori nello stesso server, con regole diverse | Lawliet ("Initial Voice Channels", più di uno) [LAWLIET], VoiceMaster (più modalità di setup) [VM] | 🟡 parziale: un generatore per server | Tabella dei generatori (categoria, modello nome, limite predefinito) | nuova |
| VOC-017 | Scegliere quali azioni può fare il proprietario, per ruolo | VoiceMaster ("Permission Management") [VM] | ❌ manca | Elenco di azioni consentite per ruolo in `/admin voice` | nuova |
| VOC-018 | Registro delle azioni fatte sui canali temporanei | VoiceMaster ("Audit Logging") [VM], TempVoice [TV] | ❌ manca: le azioni del proprietario (rinomina, blocco, espulsione, cessione) non lasciano traccia | Riga di log per rinomina, blocco, espulsione, cessione; motivo ≤ 512 | nuova |
| VOC-019 | Configurazione iniziale con un solo comando che crea categoria e canali | TempVoice (`/setup`) [TV] | 🟡 parziale: `/voicetemp-setup` chiede canale e categoria già esistenti | Passo del wizard che li crea (M 10.14) | M 10.14 |
| VOC-020 | Configurazione dal sito | VoiceMaster [VM], TempVoice [TV] | ❌ manca | Pagina del pannello web | NF-20 |
| VOC-021 | Ruolo dato a chi è in un certo canale vocale | Astro ("Voice Roles") [ASTRO] | ❌ manca | Vedi RUO-044 nel file 09 | nuova |

## Fonti

Lette il 4/10/2026.

- `[VM]` VoiceMaster — https://voicemaster.xyz · https://top.gg/bot/472911936951156740
- `[TV]` TempVoice — https://tempvoice.xyz · https://tempvoice.xyz/setup · https://top.gg/bot/762217899355013120
- `[ASTRO]` Astro — https://astro-bot.space
- `[LAWLIET]` Lawliet — sorgente ufficiale https://github.com/Aninoss/lawliet-bot (`configuration_en_us.properties`, voci `autochannel_*`)
- `[MEE6]` MEE6 — https://help.mee6.xyz/en/articles/710936-mee6-free-vs-premium-plans-comparison (solo il dato "canali temporanei: 100, premium"; nessuna funzione in più rispetto a iYokai)

Non letti su fonte ufficiale:
- **TempVoice**: il sito non elenca i singoli bottoni del menu né i
  comandi `/voice`; la pagina premium non dice cosa è a pagamento. Sono
  in tabella solo le funzioni scritte sul sito e sulla scheda top.gg.
- **Astro**: la documentazione (`docs.astro-bot.space`) non è
  leggibile; in tabella c'è solo ciò che dice la pagina principale.
- **Maki**: pagina dei comandi non leggibile.

## Conteggio

21 righe: 16 ❌ e 5 🟡.
