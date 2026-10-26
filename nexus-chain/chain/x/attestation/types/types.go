package types

const ModuleName = "attestation"

type Status string

const (
	StatusAnchored Status = "ANCHORED"
	StatusRevoked  Status = "REVOKED"
)

type Attestation struct {
	ID             string `json:"id"`
	SubjectRef     string `json:"subject_ref"`
	SchemaID       string `json:"schema_id"`
	PayloadHash    string `json:"payload_hash"` // hex sha256; never raw PII
	Signer         string `json:"signer"`
	SignatureHex   string `json:"signature_hex"`
	PubKeyHex      string `json:"pubkey_hex"`
	ObservedAtUnix int64  `json:"observed_at_unix"`
	AnchoredHeight int64  `json:"anchored_height"`
	Status         Status `json:"status"`
}
