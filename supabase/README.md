# Supabase Setup

Apply `migrations/0001_init.sql` to create demo alert and detection-event tables plus the `thermal-clips` storage bucket.

Backend tests use `InMemoryBackend`; they do not require Supabase credentials or network access.
