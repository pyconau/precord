-- Schema for precord.
--
-- The monitor issues "SELECT *" against both tables and maps the result onto
-- its dataclasses positionally, so column order here is significant.

CREATE TABLE IF NOT EXISTS pending (
    order_code  text        NOT NULL,
    position    integer     NOT NULL,
    state_token text        NOT NULL,
    created     timestamptz NOT NULL,
    nickname    text,
    roles       bigint[]    NOT NULL DEFAULT '{}',
    PRIMARY KEY (order_code, position)
);

CREATE UNIQUE INDEX IF NOT EXISTS pending_state_token_idx ON pending (state_token);

CREATE TABLE IF NOT EXISTS active (
    order_code text        NOT NULL,
    position   integer     NOT NULL,
    user_id    text        NOT NULL,
    created    timestamptz NOT NULL,
    nickname   text,
    roles      bigint[]    NOT NULL DEFAULT '{}',
    PRIMARY KEY (order_code, position)
);
