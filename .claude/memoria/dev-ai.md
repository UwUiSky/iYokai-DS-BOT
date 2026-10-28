# Memoria di dev-ai

## Aggiornata
29/10/2026 · ramo `feat/r12ai` · giro r12 (agente r12ai)

## In corso
- Giro r12 parziale. Prossimo passo: riepilogo a orario (migrazione 0425 per `ultimo_testo`; tabelle 0422 già pronte:
  `ai_riepiloghi`, `ai_avvisi_parole`), poi ticket, 25.77, owner, app/pannello, voce (#142), 25.100.

## Fatto
- r12: assistente locale/vicini/piano (`core/ai_ricerca_logic.py`, `cogs/ai/_assistente.py`), boss (`cogs/ai/boss.py`),
  dungeon, misteri, spirito/frammenti, tema al setup + nomi a tema (`core/lore_nomi_logic.py`), etichetta segnalazioni,
  `/ai staff` (incidente, regola, cerca-log), ricerca web (`core/ricerca_web*.py`). Migrazioni 0420-0422. D42-D44.

## Cose imparate
- Helper di cog senza `setup`: nome con `_` iniziale (la scoperta li salta).
- `CogConGruppi` con `cog_load` proprio: chiamare `super().cog_load()`.
- Dopo `defer()` le risposte vanno con `followup.send`; i test vecchi vanno adattati.
- `interaction_check` ridefinito deve chiamare `super()`; i metodi repo con chiamante si tolgono da KNOWN_UNCALLED.
- Il guardrail scarta testi con "ignora le istruzioni": l'AI non parte, vale la risposta locale.
- clean_db non svuota tutte le tabelle tra test: usare guild diversi.
- Pesi: `/ai` ~4000 (17 figli), `/utility` ~6100 (resta poco), `/automod` e `/owner` pieni.

## Aperto
- Vedi "In corso". Testi AI solo in italiano. `/level` card PNG non usa i nomi a tema (solo l'embed di riserva).
