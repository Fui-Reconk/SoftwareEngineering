-- Staff identities and sessions stay in the identity file, outside evaluation data.
CREATE TABLE identity.account (
    user_id TEXT PRIMARY KEY NOT NULL,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'teacher', 'auditor')),
    is_active INTEGER NOT NULL DEFAULT 1
        CHECK (typeof(is_active) = 'integer' AND is_active IN (0, 1)),
    created_at INTEGER NOT NULL CHECK (typeof(created_at) = 'integer')
);

-- Store only a digest of each bearer token, never the client-visible token.
CREATE TABLE identity.auth_session (
    token_hash TEXT PRIMARY KEY NOT NULL CHECK (length(token_hash) = 64),
    user_id TEXT NOT NULL REFERENCES account (user_id) ON DELETE CASCADE,
    expires_at INTEGER NOT NULL CHECK (typeof(expires_at) = 'integer')
);

CREATE INDEX identity.idx_auth_session_user ON auth_session (user_id);
CREATE INDEX identity.idx_auth_session_expiry ON auth_session (expires_at);

CREATE TABLE identity.login_throttle (
    username_hash TEXT PRIMARY KEY NOT NULL CHECK (length(username_hash) = 64),
    failures INTEGER NOT NULL CHECK (typeof(failures) = 'integer' AND failures >= 1),
    window_start INTEGER NOT NULL CHECK (typeof(window_start) = 'integer')
);

CREATE INDEX identity.idx_login_throttle_window ON login_throttle (window_start);
