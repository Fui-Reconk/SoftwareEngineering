-- Historical account numbers do not establish anyone's real name.
ALTER TABLE identity.account ADD COLUMN display_name TEXT NOT NULL DEFAULT '';
