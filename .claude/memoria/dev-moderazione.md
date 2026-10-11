# Memoria dev-moderazione
## Aggiornata
2026-10-11 (sera), ramo feat/sicurezza-audit (base 90bbeb2), worktree /home/claude/wt/sic.
## In corso
Revisione di cacciatore e revisore applicata (commit E): smoke, commit, push. Nessun file a meta.
## Fatto
- A 8895c79 anti-nuke (SIC-001/002/005-010/017-020/025, #59 3.5)
- B e684371 anti-raid (SIC-003/004/022), quarantena condivisa
- C ccdc53b security_score, heatmap, ban globale (SIC-044/046)
- D 012e083 spam-trap, verify, invite_sync, controlla
- E revisione: solo-chi-gestisce, fiducia in core, una punizione per attacco, rilascia unico, quarantena fail-open, ban globale (revoca/staff/indici), /modban unban, resolve_voce in core/security_audit.py
- Doc: revisione/03-verifica/AUDIT_SICUREZZA.md, VERIFICA_LIVE.md, SPEC §7, COMMAND_LIST (228)
- #59 righe 3.1-3.17 gia fatte
## Cose imparate
- Tabelle sicurezza create in security_repo.run_migrations, non in core/migrations (0024-0026 non servivano)
- Lock asyncio a livello modulo: usare WeakKeyDictionary per loop
- MFALevel non e int: usare .value
- Smoke supera il limite di 2 min del tool: lanciarlo in background su log; mai due pytest insieme sullo stesso DB (clean_db svuota)
- Test degli enable/cog con server finto: patchare ruolo_quarantena (ora si crea all'attivazione)
- Controllo mutazioni: script in scratchpad (sostituisce una riga, lancia i test, ripristina)
## Aperto
- 3.18 (serve router canali NF-01, stub)
- alt_detection (OAuth #92), lockdown/panic SIC-011-015 (#100), ban_appeal_logic (#101)
- SIC-016, 021, 023-038, 039-043, 045, 026
- Fuori perimetro: utility/greetings.py manca hook raid_in_corso (M 10.16)
- Decisione aperta: quarantena fallita non ripiega su kick/ban (la config 'ban' lo fa gia)
- Vanity URL via http.request non verificata su Discord reale
