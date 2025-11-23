-- Fix tasks table to allow NULL agent_id
-- Tasks are created without an agent, agents claim them when they pick them up

ALTER TABLE tasks ALTER COLUMN agent_id DROP NOT NULL;

