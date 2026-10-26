# ADR 0004: No sequential nonces

Banks have many operators signing concurrently. Replay protection is:

1. `chain_id` inside signed digests
2. bounded `valid_until_height`
3. `seen/` window of transaction IDs
4. permanent UETR uniqueness

Submission is idempotent: duplicates return the same `tx_id`.
