-- A printed GST invoice must not change after the sale: snapshot the line HSN and the place of
-- supply. NULL on rows from before this migration (readers fall back to the live values).
-- ADD COLUMN does not fire the final-bill immutability triggers (they guard UPDATE/INSERT/DELETE).
ALTER TABLE bill_line ADD COLUMN hsn TEXT;
ALTER TABLE bill ADD COLUMN place_of_supply_state TEXT;
