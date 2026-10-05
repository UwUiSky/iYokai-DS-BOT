# VOCE_YOKAI.md — La voce di iYokai

Specifica scritta dall'owner il 05/10/2026 (Parte 1, riportata com'è)
e note per realizzarla (Parte 2). Decisione: D22. Lavoro: issue #142.

> **Aggiornamento dell'owner, stesso giorno (vale questo):** il motore
> è **Kokoro-82M** con la voce italiana **`if_sara`**. Tutto in
> locale, veloce, gratuito, semplice da integrare nel bot Python.
> Niente servizi cloud. Qwen3-TTS (Parte 1, punti 1 e 9) resta come
> alternativa già studiata, se Kokoro non bastasse.
>
> Cosa cambia nelle note della Parte 2:
> - **Niente servizio a parte**: Kokoro gira dentro il bot, sul
>   processore, in un thread a parte e in coda. Provato il 05/10: 34
>   secondi di voce in 14 secondi di calcolo su 2 CPU.
> - **Timbro sempre uguale** per costruzione: la voce è una sola.
> - **`VoiceProfile`** con `voice`, `speed`, `pitch`, `volume`, `pause`,
>   `style`. Kokoro regola da solo soltanto la velocità: intonazione e
>   volume si correggono dopo, sull'audio; le pause si ottengono dicendo
>   una frase alla volta. Prototipo in `scripts/prova_voce.py`.
> - **Limite da conoscere**: Kokoro non ha un comando per l'emozione né
>   per la voce "breathy". Il carattere dei contesti viene da velocità,
>   pause, piccola correzione dell'intonazione e, soprattutto, da **come
>   è scritta la frase**. Per questo il testo va preparato per la
>   prosodia prima della sintesi (`core/voice_text_logic.py`).
> - **Lingue di Kokoro**: italiano, inglese, spagnolo, francese,
>   portoghese, giapponese, cinese, hindi. Per le altre lingue serve una
>   voce di un altro motore.
> - **Giudizio dell'owner sui primi campioni Kokoro** (voce mescolata
>   con altre): R moscia e parole impastate. I campioni nuovi usano
>   `if_sara` pura, una frase alla volta: in attesa del giudizio.

## Parte 1 — Specifica dell'owner

```text
iYokaiミ — Voice Message TTS Specification

Voglio implementare nel bot Discord di iYokaiミ un sistema completo di Text-to-Speech per generare voice message e, dove tecnicamente possibile, audio da riprodurre nei canali vocali.

1. Motore TTS da utilizzare

Come prima scelta valuta Qwen3-TTS 12Hz 1.7B VoiceDesign.

Repository ufficiale:
https://github.com/QwenLM/Qwen3-TTS

Model:
Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign

Il motivo della scelta è che il modello supporta il voice design tramite descrizione testuale, controllo della prosodia/emozione e italiano. L'obiettivo è poter definire una voce proprietaria del bot senza dipendere da una voce commerciale preconfezionata.

Il sistema deve essere progettato in modo modulare:

Discord Bot
→ Voice Message / TTS Service
→ Text normalization
→ Context / Tone selection
→ Qwen3-TTS
→ WAV/PCM
→ eventuale conversione FFmpeg/Opus
→ Discord

Il TTS deve essere isolato dal resto del bot tramite un servizio/modulo dedicato, così da poter sostituire Qwen3-TTS in futuro senza modificare il sistema di voice messages.

Se Qwen3-TTS 1.7B risultasse troppo pesante per l'ambiente di deployment, prevedere come fallback il modello 0.6B oppure un backend TTS alternativo.

2. Obiettivo della voce

La voce deve essere chiaramente quella di una donna adulta molto giovane, indicativamente con una percezione vocale nell'area 18–20+.

IMPORTANTE:

"giovane" non significa infantile.

La voce NON deve sembrare quella di una bambina, adolescente minorenne o personaggio infantile.

Deve avere una maturità vocale adulta, pur mantenendo freschezza, leggerezza e giovinezza.

L'effetto desiderato è:

- giovane donna adulta
- femminile
- fresca
- sicura di sé
- morbida
- molto naturale
- leggermente sensuale
- magnetica
- giocosa quando il contesto lo permette
- mai caricaturale
- mai eccessivamente acuta
- mai infantile
- mai robotica

3. Timbro

Il timbro dovrebbe essere:

- femminile
- morbido
- caldo
- leggermente breathy
- abbastanza vicino
- con una risonanza naturale
- medio/medio-alta, ma non soprano
- con una leggera componente vellutata
- con consonanti nitide
- con vocali morbide
- con una piccola quantità di aria nella voce

Evitare:

- voce troppo acuta
- voce da anime caricaturale
- voce da bambina
- voce eccessivamente nasale
- voce telefonica
- voce metallica
- voce da assistente virtuale
- voce eccessivamente profonda
- voce adulta/matura
- eccessivo breathiness che renda le parole poco comprensibili

4. Personalità vocale

La personalità dovrebbe ricordare una giovane donna estremamente sicura di sé, intelligente e consapevole del proprio fascino.

Non deve però sembrare una "voce porno".

La componente sensuale deve essere soprattutto una caratteristica del timbro e della prosodia.

Immagina una personalità:

"confident, playful, elegant, teasing, warm and slightly seductive."

La voce deve poter passare naturalmente da:

"Buongiorno a tutti, come state?"

a:

"Attenzione, questa azione non è consentita."

senza sembrare che siano due persone differenti.

5. Prosodia

La prosodia è fondamentale.

Non voglio una lettura piatta.

Utilizzare:

- variazioni naturali del pitch
- pause brevi e realistiche
- enfasi sulle parole importanti
- ritmo leggermente variabile
- intonazione femminile naturale
- finali delle frasi non sempre uguali
- piccole variazioni di velocità
- micro-pause prima delle informazioni importanti

La voce deve sembrare generata da una persona che sta effettivamente parlando, non da un sistema che sta leggendo una stringa.

6. Velocità

Velocità base:

circa 0.95–1.05x rispetto al parlato naturale.

Per messaggi scherzosi/pubblici:

~1.00–1.05x

Per moderazione:

~0.95–1.00x

Per annunci importanti:

~0.90–0.95x

Non rallentare artificialmente la voce per renderla "sensuale".

La sensualità deve provenire dal timbro e dalla prosodia, non da una velocità eccessivamente lenta.

7. Tono in base al contesto

La stessa identità vocale deve essere mantenuta in tutti i contesti.

Cambiare solamente:

- formulazione della frase
- livello di formalità
- energia
- quantità di ironia
- quantità di calore
- prosodia

PUBLIC / GENERAL

Tono:

- dolce
- amichevole
- scherzoso
- energico
- spontaneo
- leggermente teasing

Esempio:

"Oooh, guarda chi si è fatto vedere! Bentornata/o nel server~"

MODERATION

Tono:

- professionale
- calmo
- autorevole
- fermo
- chiaro
- non aggressivo

Esempio:

"Attenzione. Questo comportamento non è consentito in questo server. Ti invito a interromperlo."

La voce rimane la stessa, ma perde quasi completamente il tono giocoso.

ANNOUNCEMENTS

Tono:

- chiaro
- leggermente più energico
- autorevole
- coinvolgente

WELCOME

Tono:

- caldo
- positivo
- amichevole
- leggermente giocoso

Esempio:

"Benvenuta nel server! Dai, vieni a dare un'occhiata in giro."

NSFW CHANNELS

Il sistema deve supportare un profilo di tono adulto e più provocatorio quando il contesto del canale lo consente.

Tuttavia la voce deve rimanere chiaramente quella di una donna adulta e il motore TTS deve essere trattato separatamente dal sistema che decide il contenuto testuale.

Non hardcodare il tono NSFW direttamente nel motore vocale.

8. Architettura consigliata

Creare un VoiceProfile configurabile.

Esempio concettuale:

VoiceProfile:
name: "iYokaiミ"
language: "it"
gender: "female"
age_perception: "young adult"
timbre: "warm, soft, slightly breathy"
pitch: "medium-high"
resonance: "natural, feminine"
personality:
confident: 0.8
playful: 0.7
warm: 0.8
seductive: 0.4
speech_rate: 1.0

Poi creare profili contestuali:

PUBLIC
MODERATION
ANNOUNCEMENT
WELCOME
NSFW

Ogni profilo deve modificare solamente i parametri di espressione, mantenendo la stessa identità vocale.

9. Prompt per il VoiceDesign

Usa questo come base per il prompt di Qwen3-TTS VoiceDesign:

"Young adult female voice, clearly adult and mature, approximately early-twenties in perceived age. Warm, feminine and naturally attractive timbre with a soft slightly breathy texture. Medium to medium-high pitch, never childish or overly high-pitched. Smooth vocal resonance, clear articulation, natural Italian pronunciation, expressive intonation and realistic conversational rhythm. Confident, playful, elegant and subtly seductive personality. The voice should feel close, warm and charismatic, with gentle teasing energy when appropriate, but remain natural and believable. Avoid anime-style exaggeration, childish qualities, cartoonish pitch, excessive breathiness, monotone delivery, robotic articulation and overly dramatic acting. The speaker should sound like a confident young adult woman speaking naturally to people in a Discord community."

Questo prompt definisce la VOCE.

Non usarlo per definire il contenuto del messaggio.

10. Text preprocessing

Prima di inviare il testo al TTS:

1. rimuovere markdown inutile
2. convertire emoji problematiche in testo oppure eliminarle
3. normalizzare URL
4. normalizzare mention Discord
5. normalizzare numeri quando necessario
6. gestire acronimi
7. evitare letture assurde di username e ID
8. inserire pause dove necessario
9. preservare la punteggiatura utile alla prosodia

Il TTS deve ricevere testo naturale, non direttamente il messaggio Discord grezzo.

11. Performance

Non generare necessariamente tutto in tempo reale durante la risposta del bot.

Implementare:

- caching
- hash del testo + voice profile
- cache audio locale
- eventuale TTL
- limite alla lunghezza del testo
- queue per richieste concorrenti
- timeout
- fallback in caso di errore

Esempio:

TTS(text, voice_profile)
→ SHA256(text + profile + model)
→ cache lookup
→ se presente: restituisci audio
→ se assente: genera
→ salva
→ restituisci audio

Questo è particolarmente importante per frasi ripetitive del bot, come warning, welcome, errori e messaggi di moderazione.

12. Discord output

Generare preferibilmente PCM/WAV internamente e convertire a Opus/codec Discord solo nello strato finale.

Non legare il modello TTS direttamente alla gestione del VoiceClient.

Separare:

TTS Engine
↓
Audio Processor
↓
Discord Voice Adapter

In questo modo sarà possibile cambiare motore TTS senza riscrivere la parte Discord.

13. Obiettivo finale

Il risultato deve essere percepito come:

"Una giovane donna adulta, sicura di sé, molto femminile, morbida, carismatica e leggermente seducente che vive all'interno dell'ecosistema iYokaiミ."

Non voglio:

"assistente vocale generica".

Non voglio:

"voce da anime".

Non voglio:

"voce da bambina".

Non voglio:

"voce da navigatore".

Voglio una vera identità vocale del bot, coerente in tutto l'ecosistema, con variazioni di personalità determinate dal contesto ma con lo stesso timbro riconoscibile.
```

## Parte 2 — Note per realizzarla

### Cosa è stato verificato (05/10/2026, scheda ufficiale del modello)

- Qwen3-TTS: licenza Apache 2.0; 10 lingue, tra cui italiano e tedesco
  (cinese, inglese, giapponese, coreano, tedesco, francese, russo,
  portoghese, spagnolo, italiano).
- Timbro, emozione e prosodia si guidano con istruzioni in linguaggio
  naturale.
- Si installa con `pip install -U qwen-tts`. L'esempio ufficiale usa
  una scheda video (`cuda`).
- Il modello VoiceDesign ha circa 1,9 miliardi di parametri.

Da verificare prima del codice: memoria video necessaria, tempi su
processore, nomi esatti delle funzioni per disegnare e per clonare la
voce (da qui non è stato possibile scaricare il modello né provarlo).

### 1. Stesso timbro sempre: disegnare una volta, poi clonare

VoiceDesign crea la voce dalla descrizione, e a ogni generazione il
timbro può cambiare un po'. Per avere **una** voce riconoscibile:

1. con VoiceDesign e il prompt del punto 9 si generano più campioni;
2. l'owner sceglie il migliore;
3. quel campione, con il suo testo, diventa la **voce di riferimento**
   del progetto (un file audio con una versione nel nome);
4. da lì in poi ogni frase si genera **clonando** quel riferimento
   (modello Base), e l'istruzione cambia solo il tono del contesto.

Se si cambia la voce di riferimento cambia la versione, e la cache
riparte: nessun miscuglio di timbri.

### 2. Dove gira il modello

Il modello vuole una scheda video. Il bot no. Per questo la voce è un
**servizio a parte**, che il bot chiama in rete locale:

```
bot ──HTTP──► servizio voce (testo, profilo, contesto) ──► audio
```

Il servizio può stare dove c'è una scheda video:
- sul PC dell'owner (RTX 3080 Ti, 12 GB), per preparare in una volta
  la **libreria delle frasi fisse** (saluti, benvenuti, avvisi,
  errori, frasi dei ticket);
- sul server del bot, se ha una scheda video;
- se non ce l'ha: modello 0.6B sul processore, in coda e con tempi più
  lunghi, oppure un motore leggero (Piper) per il solo testo che
  cambia ogni volta.

Il bot funziona anche con il servizio spento: usa la cache e, se la
frase non c'è, manda solo il testo.

### 3. Chiave della cache

`SHA256(testo normalizzato + profilo + contesto + modello + versione
della voce di riferimento)`. Le frasi fisse non scadono. Il resto ha
una scadenza e la cartella ha un tetto di spazio.

### 4. Uscita verso Discord

| Uscita | Come | Limiti |
|---|---|---|
| Messaggio vocale | OGG Opus 48 kHz mono, durata e forma d'onda (256 punti), chiamata diretta all'API | Un vocale non porta testo né bottoni: i bottoni "Trascrivi" e "Nella mia lingua" stanno nel messaggio sotto |
| Canale vocale | Il file va a Lavalink come brano locale o via HTTP | Il bot usa wavelink: nello stesso server non può usare insieme anche la voce diretta di discord.py. Si passa sempre da Lavalink |

### 5. Contesti e contenuto

- I cinque contesti (PUBLIC, MODERATION, ANNOUNCEMENT, WELCOME, NSFW)
  cambiano solo l'espressione. Il **testo** lo decide un altro strato.
- NSFW: solo nei canali segnati NSFW (D22). Il motore non lo sa e non
  deve saperlo: riceve un testo e un profilo.
- Moderazione: la voce può accompagnare l'avviso, ma il **testo resta
  sempre** e fa fede.
- La voce è e resta quella di una donna adulta (punti 2, 3 e 13 della
  specifica): nessun profilo può alzarne l'intonazione verso una voce
  infantile.

### 6. File da creare

| File | Cosa contiene |
|---|---|
| `core/voice_profile.py` | `VoiceProfile` e i profili di contesto |
| `core/voice_text_logic.py` | Pulizia del testo prima della sintesi (punto 10): logica pura, con test |
| `core/voice_cache.py` | Chiave, ricerca, salvataggio, scadenza, tetto |
| `core/voice_audio.py` | WAV → OGG Opus, durata, forma d'onda |
| `core/voice_client.py` | Chiamata al servizio voce, coda, tempo massimo, ripiego |
| `core/discord_raw.py` | Invio del messaggio vocale (chiamata diretta) |
| `servizio_voce/` | Il servizio a parte con il motore (Qwen3-TTS; motori di riserva) |
| `scripts/prova_voce_qwen.py` | Prova a mano sul PC con scheda video |
