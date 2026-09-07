-- Extensión aditiva del contrato de unidades para preservar tipología/ubicación.
-- No elimina ni transforma columnas existentes.

ALTER TABLE raw_mercado.unidades
    ADD COLUMN IF NOT EXISTS tipologia_ubicacion TEXT;

ALTER TABLE raw_cygnus.unidades
    ADD COLUMN IF NOT EXISTS tipologia_ubicacion TEXT;
