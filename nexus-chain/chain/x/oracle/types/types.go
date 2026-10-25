package types

const ModuleName = "oracle"

type Report struct {
	ID            string   `json:"id"`
	FeedID        string   `json:"feed_id"`
	Value         string   `json:"value"` // decimal string or integer minor units as string
	Decimals      uint32   `json:"decimals"`
	Reporters     []string `json:"reporters"`
	QuorumMet     bool     `json:"quorum_met"`
	TimestampUnix int64    `json:"timestamp_unix"`
	ExpiresHeight int64    `json:"expires_height"`
}
