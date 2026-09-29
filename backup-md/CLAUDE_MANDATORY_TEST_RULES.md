# Regole OBBLIGATORIE per Claude (e qualsiasi AI) — test live iYokai

**Owner:** UwUiSky  
**Scopo:** impedire di dichiarare “tutto funziona” senza ambienti reali, e impedire di pubblicare segreti.

Questo file **non** contiene token, password o connection string.  
I segreti si chiedono **in chat privata con l’owner**, si usano solo in runtime locale, **mai** in commit, issue, PR, log pubblici, README, SPEC, REVIEW.

---

## 0. Principio

Analisi statica del codice **non basta** per chiudere bug di runtime (ticket close, setup, DB, music, OAuth, backup).  
Prima di affermare che una feature è verificata end-to-end, valgono le sezioni 1–3.

---

## 1. Segreti — DIVIETI ASSOLUTI

1. **NON** scrivere mai in repository (file, commit, issue, commenti GitHub, CI log pubblici):
   - token Discord bot
   - `DATABASE_URL` / password Postgres / host Aiven con credenziali
   - `LAVALINK_PASSWORD` e URI con secret
   - OAuth client secret, encryption keys, webhook secret
2. **NON** committare file `.env` (deve restare in `.gitignore`).
3. **NON** ripetere i segreti ricevuti in chat dentro issue o commit message.
4. Se un segreto finisce per errore in un commit: **fermare tutto**, avvisare l’owner, far **rigenerare** il secret (Discord Portal / Aiven), non “nasconderlo” con un commit successivo che lo lascia nella history.

---

## 2. Token Discord — OBBLIGATORI prima di test live sul bot

Il loader attuale (`core/config.py`) richiede **8** token per avviare il processo:

| Variabile | Ruolo |
|-----------|--------|
| `YOKAI_BOT_TOKEN` | Bot principale |
| `YOKAI_CREATOR_TOKEN` | Creator (backup) |
| `MUSIC_TOKEN_1` … `MUSIC_TOKEN_5` | Istanze music |
| `NSFW_TOKEN` | App NSFW |

Inoltre obbligatori per un run sensato:

| Variabile | Ruolo |
|-----------|--------|
| `OWNER_ID` | Owner Discord (int) |
| `MAIN_GUILD_ID` | Guild di sviluppo/test (int) |
| `DATABASE_URL` | Postgres (vedi §3) |

### Comportamento obbligatorio di Claude

1. **Prima** di procedere a test live / “verifico che parte il bot” / claim di fix runtime su Discord:  
   **chiedere in chat all’owner** i token (o conferma che esistono già in un `.env` locale non committato).
2. Usarli **solo** per eseguire o guidare test; non copiarli in alcun artefatto del repo.
3. A fine ciclo di test (o su richiesta owner): ricordare di **rigenerare (reset) tutti i token** nel Developer Portal.
4. Contesto attuale: bot **non in produzione / zero server utenti**; i token sono di sviluppo, ma le regole anti-leak restano identiche.

---

## 3. PostgreSQL (Aiven o altro) — OBBLIGATORIO per test DB reali

### Comportamento obbligatorio di Claude

1. Prima di dichiarare migrate / query / economy / tickets / backup tables / scheduler OK in condizioni reali:  
   **chiedere in chat** la `DATABASE_URL` (o host/user/password/db/porta e se serve SSL) **senza** pubblicarla.
2. Impostare/usare solo via ambiente locale, es.:
   ```bash
   export DATABASE_URL='postgresql://...@...aivencloud.com:..../defaultdb?sslmode=require'
   ```
   Oppure file `.env` locale (non tracciato da git).
3. Aiven in free/test tipicamente richiede **SSL** → nella URL includere `sslmode=require` se non già presente.
4. **Non** usare credenziali Aiven di test in issue o in esempi di codice committati.
5. A fine test: l’owner può distruggere il servizio Aiven o ruotare la password; Claude deve indicare solo di aggiornare `DATABASE_URL` nel `.env` locale, senza scrivere la stringa nel repo.

### Dopo i test (istruzione per l’owner, da ricordare)

- Cambiare `DATABASE_URL` verso Postgres definitivo (VPS o nuovo servizio).
- Opzionale: eliminare il servizio Aiven di test dal pannello Aiven.
- Nessuna modifica al codice Python necessaria per il solo cambio URL.

---

## 4. Cosa si può fare SENZA segreti

Consentito sempre:

- lettura e review del codice
- aperture/aggiornamenti issue **senza** credenziali
- test di logica pura / unit test che non richiedono Discord o DB remoto
- proposte di patch in chat o PR **senza** hardcodare secret

**Vietato** dichiarare:

- “ho verificato live su Discord” senza §2
- “ho verificato il database / le migrate in condizioni reali” senza §3
- “tutto il bot è 100% funzionante” basandosi solo su test che evitano i casi rotti (vedi `REVIEW.md` e issue audit)

---

## 5. Checklist minima prima di un claim “fix verificato”

- [ ] Token §2 ricevuti in chat (o `.env` locale confermato dall’owner) — **non** nel repo
- [ ] `DATABASE_URL` Aiven (o altro Postgres di test) ricevuta in chat — **non** nel repo
- [ ] Bot avviato senza crash di config
- [ ] `run_migrations` / avvio DB ok
- [ ] Smoke sui bug noti prioritari (es. ticket close, setup, permessi mod) documentato in issue **senza** log con secret

Per music/radio locali serve anche Lavalink (self-host o nodo configurato); senza di esso non si può certificare play/local.

---

## 6. Riferimenti issue (audit, non segreti)

- Indice audit: issue **#51**
- Self-host Lavalink: **#47**
- Docs nodi pubblici: **#48**
- Setup per categoria: **#49**
- AI mancante: **#50**
- GDPR/retention: **#46**

---

*Firmato come istruzione owner per Claude / AI collaboranti. Aggiornare questo file solo con regole, mai con valori secret.*
