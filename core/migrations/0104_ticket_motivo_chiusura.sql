-- TKT-056 (#120): il motivo di chiusura si salva col ticket.
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS close_reason TEXT;
