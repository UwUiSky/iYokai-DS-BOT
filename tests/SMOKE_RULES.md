# Regole obbligatorie per gli smoke test (e test “unit” Discord)

Scopo: evitare test **verdi ma non veritieri** — cioè suite che passano mentre il bot fallirebbe contro le API reali di Discord o il comportamento reale di discord.py.

Fonti canoniche (consultare sempre la versione corrente):

- Discord API: https://discord.com/developers/docs/reference
- Limits (messaggi, embed, select, comandi): https://discord.com/developers/docs/resources/channel e sezioni Application Commands
- Application Commands / options: https://discord.com/developers/docs/interactions/application-commands
- Privileged intents: https://discord.com/developers/docs/topics/gateway#privileged-intents
- discord.py: https://discordpy.readthedocs.io/

---

## 1. Cosa uno smoke **deve** fare

Uno smoke minimo (load cog + nomi comandi) è utile ma **non sufficiente** per dichiarare una feature OK.

Per ogni area critica lo smoke (o un test behavior collegato) deve, dove applicabile:

1. **Simulare le firme reali** di discord.py (`create_autospec` / fakes in `tests/support/discord_fakes.py`).
   - Vietato: oggetti finti fatti a mano che accettano kwargs inesistenti (es. `channel.delete(delay=10)` → in discord.py solleva `TypeError`; un fake “gentile” lo nasconde).
2. **Rispettare i limiti API Discord** nel design del test e nelle asserzioni:
   - Select menu: **max 25** opzioni per select.
   - String select / options lunghezze e vincoli documentati.
   - Max **100** comandi slash globali (top-level) per applicazione.
   - Limiti lunghezza: content messaggio, embed (title/description/fields), modal, button label/custom_id.
   - Rate limits: non assumere burst illimitati in test di loop/scheduler.
3. **Rispettare gli intent**: se il codice usa `message.content`, il test non deve fingere content valorizzato quando in produzione `message_content` è off (vedi issue `#6` / `#36` / `#39`).
4. **Permessi**: se un comando è pensato solo per moderatori, il test deve verificare `default_permissions` / `has_permissions` (o documentare esplicitamente che manca — non far passare il silenzio come OK).
5. **Guild vs DM**: comandi guild-only non devono essere considerati “ok” se in DM non c’è guard e il codice accede a `interaction.guild.id` senza check.

---

## 2. Cosa uno smoke **non** può certificare da solo

Anche se verde, **non** equivale a:

- verifica live su Discord (token, guild reale, permessi bot nel server)
- voice / Lavalink / radio 24/7
- OAuth restore end-to-end
- backup Creator multi-guild
- migrazioni su Postgres di produzione

Per quelli: `backup-md/CLAUDE_MANDATORY_TEST_RULES.md` + `VERIFICA_LIVE` (in history / backup-md) + issue `#53`.

---

## 3. Fakes e discord.py — regole pratiche

| Regola | Perché |
|--------|--------|
| Usare `tests/support/discord_fakes.py` (autospec) | Le API discord.py rifiutano argomenti sconosciuti; i fake devono fare lo stesso |
| Non stubbare via metodi che in API non esistono | Nasconde crash di produzione (es. BUG-1 ticket close) |
| `Interaction.response` / `followup` con stati realistici (`is_done`) | Evita doppi respond silenziosi |
| View persistenti: `timeout=None` + `custom_id` e `is_persistent()` | `bot.add_view` rifiuta view non persistenti |
| Select options ≤ 25 | Limite API; un test che costruisce 30 opzioni e si aspetta successo è **non veritiero** |

---

## 4. Checklist “questo smoke è veritiero?”

- [ ] Fallirebbe se chiamassi un metodo discord.py con firma sbagliata?
- [ ] Rispetta limiti documentati (25 select, lunghezze, comandi)?
- [ ] Non assume intent/privileged che il bot non ha in config?
- [ ] Non marca come OK assenza di `default_permissions` su comandi mod?
- [ ] Per bug già noti (issue aperte), esiste un test che **fallisce** finché il bug c’è (non solo load cog)?

Se una risposta è no → lo smoke **non** è sufficiente; serve test behavior o live.

---

## 5. Aggiornamento di questi smoke

Quando si tocca un cog:

1. Se si aggiunge un comando soggetto a limiti API → asserire il limite nel test.
2. Se si fixa un bug di firma API → il test deve usare autospec e riprodurre il fallimento pre-fix.
3. Non aggiungere nomi a insiemi `KNOWN_*` solo per far passare la suite.

---

*iYokai Advisor Bot — regole vincolanti per chi scrive o rivede test in `tests/`.*
