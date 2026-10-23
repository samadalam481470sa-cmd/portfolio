# ADR 0005: FIFO with tail-removal netting

Gross settlement is strict per-debtor FIFO. Gridlock resolution removes the newest
violating units (LIFO among lowest priority) so each debtor's settled set remains a
FIFO prefix. The algorithm is a documented heuristic, not an optimal MIP.
