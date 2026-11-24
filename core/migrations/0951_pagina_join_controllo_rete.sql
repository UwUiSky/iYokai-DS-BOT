-- BKP-040 (D127, D130, #121): regola di ammissione alla pagina di consenso: controllo VPN e di rete (VER-026) prima del consenso.
-- È solo un interruttore: l'IP non si salva mai (il controllo lo usa al momento della richiesta e lo scarta).
ALTER TABLE web_panel_pubblico ADD COLUMN IF NOT EXISTS join_controllo_rete BOOLEAN NOT NULL DEFAULT FALSE;
