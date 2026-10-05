# Gap analysis: Wick + Protector + AI Server Builder + Reputazione + Channel Obfuscation 16/11/2026

**Tipo:** ricerca / backlog (non implementazione)  
**Firma:** iYokai Advisor Bot  
**Repo analizzata:** `cogs/security/*`, `cogs/utility/backup.py`, `cogs/automod/*`, `cogs/moderation/*`, `revisione/01-analisi/catalogo/18-ai.md`, `FUNZIONI_AI.md`, `CONFRONTO_BOT.md`, `NUOVE_FUNZIONI.md`.

Obiettivo: documentare cosa fanno Wick e Protector, cosa ha iYokai nel codice, gap, mitigazioni API Discord legali, differenziatori AI Server Builder e reputazione (no globale da sanzioni).

---

## Indice

1. [Stato iYokai security (codice reale)](#1-stato-iyokai-security-codice-reale)
2. [Wick — feature map](#2-wick--feature-map-dettagliata)
3. [Protector — feature map](#3-protector--feature-map-dettagliata)
4. [Matrice gap completa](#4-matrice-gap-completa)
5. [Channel Obfuscation 16/11/2026](#5-channel-obfuscation-16112026)
6. [Policy permessi multi-istanza](#6-policy-permessi-multi-istanza)
7. [AI Server Builder (AI-025)](#7-ai-server-builder-ai-025)
8. [Sistema di reputazione](#8-sistema-di-reputazione)
9. [Backlog A–G](#9-backlog-prioritizzato-ag)
10. [Non-goals](#10-non-goals-espliciti)
11. [Acceptance criteria](#11-acceptance-criteria)
12. [Riferimenti](#12-riferimenti)

---

## 1. Stato iYokai security (codice reale)

### 1.1 File presenti

| Path | Ruolo |
|------|--------|
| `cogs/security/anti_nuke.py` | Anti-nuke a soglie + recovery da cache evento |
| `cogs/security/anti_raid.py` | Join rate, età, username, avatar → quarantena / verification level |
| `cogs/security/lockdown.py` | **SCHELETRO VUOTO** (issue #100, nessun comando) |
| `cogs/security/verify.py` | Button/reaction, captcha testuale, età, mutual, WL/BL |
| `cogs/security/spam_trap.py` | Honeypot: ban, transcript, appeal, purge, cleanup webhook/inviti |
| `cogs/security/alt_detection.py` | Alt detection |
| `cogs/security/global_ban.py` | Global ban (lista bot, non reputation sociale) |
| `cogs/security/permission_heatmap.py` | Heatmap permessi |
| `cogs/security/security_score.py` | Score (non unificato in UX join come Protector) |
| `cogs/security/invite_sync.py` | Invite sync |
| `cogs/utility/backup.py` | Main/backup **server pair** (Xenon-like), non snapshot anti-nuke |
| `cogs/automod/*` | Automod + escalation |
| `cogs/moderation/*` | Azioni, cases, softban/mute |
| `cogs/logging/*` | Log |

### 1.2 Anti-nuke — cosa fa davvero

**Categorie monitorate (soglie configurabili):** canali, ruoli, webhook (`on_webhooks_update`), emoji/sticker, ban/kick.

**Autore:** sempre da audit log (retry 0s / 1s / 1s).

**Punizione:** owner → nulla; `ban` → ban; altrimenti umani → strip ruoli (managed tenuti); bot → kick.

**Trusted:** `trusted_ids`.

**Recovery (`recovery_enabled`):**
- Non usa snapshot DB persistente
- Usa oggetto in cache su `on_guild_*_delete`
- Ricrea tipo/nome/permessi/posizione; ruoli re-add fino a 500 membri
- Coda `_in_attesa` sotto soglia
- Skip nome `___hidden___` ma **non** flag `CHANNEL_OBFUSCATED`

**Config:** `Manage Server` può spegnere tutto → **non** owner-only. Premium candidato.

### 1.3 Anti-raid

Join rate, età account, username, avatar → quarantena e/o verification level. Ruolo `Quarantined` + overwrite. Bot in join **ignorati**. Alert DM + canale.

### 1.4 Forte / debole

| Pezzo | Verdetto |
|-------|----------|
| Spam trap | **Forte** |
| Verify | Base; captcha solo testo; gate incompleto |
| Lockdown/panic | **Assente** |
| Backup | Altro prodotto, non restore nuke |
| Owner-only modules | **Assente** |
| Staff guard / impersonation | **Assente** |
| Coordinated spam | **Assente** |
| Snapshot DB | **Assente** |

---

## 2. Wick — feature map dettagliata

Fonti: docs.wickbot.com/intro/features, FAQ, review 2026.

### Anti-Nuke
- Canali/ruoli/ban/kick/webhook
- Bypass: liberare Q, dangerous perms su Q o qualsiasi ruolo, vanity
- Quarantine; **Panic Mode** + **miniWick**; Restore da Imaging o best-effort

### Heat System
Score adattivo multi-segnale, decay, webhook duri, multiplier timeout, Heat Panic, lockdown mass mention.

### Join Gate / Raid / Verify
No avatar, account nuovi, bot non autorizzati, bot non verificati, invite profilo, username; Join Raid; verification multi-mode.

### Governance
Extra Owners / Trusted immune.

### Limiti
No member recovery di community; premium; no AI builder; snapshot nov meno esplicito di Protector.

---

## 3. Protector — feature map dettagliata

Fonti: protector-bot.com/docs (Ott 2026).

### Setup
Ruolo in cima; `/autoconfig` 1–3; `/diagnostic`; dashboard web apply lato bot.

### Moduli protetti
Anti-raid/nuke/spam/webhook, bot quarantine, coordinated raid: solo owner o **security role**; grant illegale → strip + DM.

### Anti-raid / spam / coordinated
Lockdown persistente; anti-spam avanzato; coordinated multi-account.

### Anti-nuke + restore
Prune, vanity, `@everyone` dangerous, private→everyone; restore da backup; report onesto post-nov.

### Bot quarantine
Default ON; undo re-grant; watch <7d / <30d.

### Altro
Phishing, NSFW locale, honeypot, risk 0–100, staff guard, compromised staff, anti-impersonation, verify image captcha + gate.

---

## 4. Matrice gap completa

Legenda: ✅ ok · ⚠️ parziale · ❌ assente

### 4.1 Anti-nuke e restore

| Capacità | Wick | Protector | iYokai | Azione |
|----------|------|-----------|--------|--------|
| Soglie canali/ruoli/webhook/ban | ✅ | ✅ | ✅ | Raffinare |
| Emoji/sticker | — | ⚠️ | ✅ | — |
| Member prune | ✅ | ✅ | ❌ | Listener |
| Vanity URL | ✅ | ✅ | ❌ | Audit |
| `@everyone` dangerous | ✅ | ✅ | ❌ | Role update |
| Private → @everyone | — | ✅ | ❌ | Detect + close |
| Dangerous perms any role | ✅ | ⚠️ | ❌ | Bitfield |
| Bypass Q watchdog | ✅ | — | ❌ | Monitor |
| Panic/lockdown | ✅ | ✅ | ❌ scheletro | #100 |
| Snapshot DB | ✅ | ✅ | ❌ | **P0** |
| Recovery solo cache | — | — | ⚠️ | + snapshot |
| Report restore | ✅ | ✅ | ⚠️ | Report |

### 4.2 Bot

| Capacità | Wick | Protector | iYokai | Azione |
|----------|------|-----------|--------|--------|
| Bot quarantine default | join gate | ✅ | ❌ | Default ON + DM |
| Undo re-grant | — | ✅ | ❌ | Listener |
| Watch bot age | — | ✅ | ❌ | Flag |
| Trusted list | ✅ | ✅ | ✅ | Ok |

### 4.3 Governance

| Capacità | Wick | Protector | iYokai | Azione |
|----------|------|-----------|--------|--------|
| Anti-* non spegnibili da Admin | Extra Owners | ✅ | ❌ | **Critico** |
| Security role strip | — | ✅ | ❌ | Audit |
| Staff guard | — | ✅ | ❌ | Implementare |
| Compromised staff | — | ✅ | ❌ | Implementare |
| Anti-impersonation | — | ✅ | ❌ | Implementare |

### 4.4 Raid / spam / verify

| Capacità | Wick | Protector | iYokai | Azione |
|----------|------|-----------|--------|--------|
| Join rate | ✅ | ✅ | ✅ | Ok |
| Risk 0–100 UI | — | ✅ | ⚠️ | Unificare |
| Coordinated spam | Heat panic | ✅ | ❌ | Window |
| Honeypot | — | ✅ | ✅ spam_trap | Forte |
| Verify gate pieno | forte | ✅ | ⚠️ | Gate |
| Image captcha | multi | ✅ | ❌ | NF-18 |

### 4.5 Novembre 2026

| Capacità | Protector | iYokai | Azione |
|----------|-----------|--------|--------|
| Flag `CHANNEL_OBFUSCATED` | ✅ | ❌ | Helper |
| Snapshot incrementale | ✅ | ❌ | DB |
| Restore onesto | ✅ | N/A | No inventare |

### 4.6 UX

| Capacità | Protector | iYokai | Azione |
|----------|-----------|--------|--------|
| Autoconfig | ✅ | ❌ | Preset |
| Diagnostic | ✅ | ❌ | Comando |

---

## 5. Channel Obfuscation 16/11/2026

- Gateway: senza VIEW_CHANNEL → offuscato, flag `1 << 17`
- HTTP guild channels: omessi
- Rilevare il **flag**, non solo `___hidden___`
- Test: toggle Developer Portal

**Mitigazione:** Admin + ruolo top su istanza mod; snapshot DB; restore onesto; no selfbot.

---

## 6. Policy permessi multi-istanza

| Istanza | Permessi |
|---------|----------|
| Main / mod / security | Administrator + ruolo top; View Audit Log |
| Music 1–5 | Connect/Speak/View — no Admin |
| Creator / backup | Solo backup (no Create Guild) |
| NSFW | Solo canali NSFW |

---

## 7. AI Server Builder (AI-025)

**Stato catalogo:** ❌ manca. Design: AI propone → admin conferma → apply con logica backup (D8).

**Vincolo:** Create Guild deprecato/non affidabile. Lavorare su **server già esistente**.

**Target:** descrizione → piano JSON validato → anteprima → apply rate-limit-safe → report → snapshot anti-nuke → pack security opzionale.

**Differenziator** vs Wick/Protector (loro non generano struttura da testo).

**Dipendenze:** NF-24 router AI; motore create condiviso col restore.

---

## 8. Sistema di reputazione

| Idea | Esito repo |
|------|------------|
| Reputazione globale da sanzioni | **RESPINTA** (BACKLOG §9) — GDPR, ban ingiusti |
| Alternativa | Profilo globale **solo positivi** opt-in |
| Risk score | Solo **nel server**, staff-only, no auto-ban da score solo |

**Fare:** risk locale unificato (score, alt, join, cases, spam_trap) + decay; profilo positivo cross-server.  
**Non fare:** propagare ban come reputation; confondere con `global_ban.py`.

---

## 9. Backlog prioritizzato A–G

### Fase A — P0 anti-nuke / novembre
- [ ] A1 Tabella snapshots canali/ruoli
- [ ] A2 Listener + reconcile
- [ ] A3 Helper flag obfuscated
- [ ] A4 Admin solo istanza mod
- [ ] A5 Test portal obfuscation
- [ ] A6 Restore da snapshot + report

### Fase B — Vettori nuke
- [ ] B1 Prune · B2 Vanity · B3 @everyone/role perms · B4 Private→everyone · B5 Watchdog Q

### Fase C — Bot + panic
- [ ] C1 Bot quarantine default + DM
- [ ] C2 Undo re-grant + age watch
- [ ] C3 Lockdown/panic (#100)

### Fase D — Governance P0
- [ ] D1 Moduli owner/security-only
- [ ] D2 Security role strip
- [ ] D3 Staff guard + compromised staff
- [ ] D4 Anti-impersonation

### Fase E — Raid/spam P1
- [ ] E1 Coordinated · E2 Risk UI · E3 Verify gate + image captcha

### Fase F — AI Server Builder
- [ ] F1 Schema · F2 Wizard · F3 Apply+snapshot · F4 Pack security · F5 Router AI + fallback

### Fase G — Reputazione P2
- [ ] G1 Risk locale documentato · G2 Profilo positivo · G3 Join alert (no auto-ban)

### UX
- [ ] X1 `/diagnostic` · X2 Autoconfig preset

---

## 10. Non-goals espliciti

1. Reputazione globale da ban/kick/warn
2. Auto-ban solo da risk score
3. Create Guild via API bot
4. Selfbot / user token
5. Member OAuth recovery tipo RestoreCord (fuori scope)
6. Duplicare issue sullo stesso gap
7. Lasciare anti-nuke spegnibile da Manage Server dopo Fase D

---

## 11. Acceptance criteria

Documento completo quando: matrice allineata al codice §1; checklist A–G tracciabile in issue figlie; policy Admin-mod e non-goals registrati; AI-025 e reputazione senza contraddire GDPR/D8/D13.

Non si chiude solo perché esiste `anti_nuke.py`.

---

## 12. Riferimenti

- https://docs.discord.com/developers/change-log (Channel Obfuscation)
- https://docs.discord.com/developers/topics/permissions
- https://docs.wickbot.com/intro/features/
- https://protector-bot.com/docs
- `cogs/security/anti_nuke.py`, `anti_raid.py`, `lockdown.py`, `spam_trap.py`, `verify.py`
- `revisione/01-analisi/catalogo/18-ai.md` (AI-025)
- `FUNZIONI_AI.md`, `CONFRONTO_BOT.md`, BACKLOG §9
- issue #100 lockdown

---

### Sintesi

iYokai: nucleo anti-nuke/raid solido ma incompleto; spam-trap forte; buchi critici vs Wick/Protector (panic, snapshot, bot quarantine, owner-only modules, staff guard, vettori prune/vanity/@everyone, flag obfuscated). Backup main/backup ≠ restore nuke. Differenziatori: AI Server Builder su guild esistente; reputazione = risk locale + profilo positivo (no globale sanzioni). Priorità: snapshot+restore+Admin mod+governance+bot Q+panic; poi AI builder e risk UX.

*— iYokai Advisor Bot*
