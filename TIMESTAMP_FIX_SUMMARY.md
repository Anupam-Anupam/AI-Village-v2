# Timestamp Fix Summary

The timestamp format for agent working directories has been updated to be more human-readable.

## Changes

- **Old Format:** `%Y%m%d_%H%M%S_%f` (e.g., `20251124_050551_751336`) - Hard to read, no separators.
- **New Format:** `%Y-%m-%d_%H-%M-%S` (e.g., `2025-11-24_05-05-51`) - ISO-like with dashes, easier to read and sort.

## Affected Files

1. `agents/agent*/agent_worker/runner.py`: Updated `timestamp` generation.
2. `agents/agent*/agent_worker/trajectory_processor.py`: Updated timestamp parsing to support the new format.

## Verification

Check the `trajectories/` directory. New tasks should create folders with the new timestamp format.

