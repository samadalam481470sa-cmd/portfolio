package types

const ModuleName = "settlement"

type Leg struct {
	From   string `json:"from"`
	To     string `json:"to"`
	Denom  string `json:"denom"`
	Amount int64  `json:"amount"`
}

type Intent struct {
	ID              string `json:"id"`
	Legs            []Leg  `json:"legs"`
	OracleFeed      string `json:"oracle_feed"` // optional; if set must be fresh
	AttestationRef  string `json:"attestation_ref"`
	ResourceLocks   []string `json:"resource_locks"` // exclusive accounts
	Status          string `json:"status"`
	SettledHeight   int64  `json:"settled_height"`
}
