package types

const ModuleName = "bank"

// MsgSend is a signed peer-to-peer transfer of the native crypto (NXN / unxn).
type MsgSend struct {
	From      string `json:"from"`
	To        string `json:"to"`
	Denom     string `json:"denom"`
	Amount    int64  `json:"amount"`
	Sequence  uint64 `json:"sequence"`
	Memo      string `json:"memo"`
	PubKeyHex string `json:"pubkey_hex"`
	SigHex    string `json:"sig_hex"`
}

type AccountMeta struct {
	Address  string `json:"address"`
	Sequence uint64 `json:"sequence"`
	PubKey   string `json:"pubkey_hex,omitempty"`
}

type Supply struct {
	Denom string `json:"denom"`
	Total int64  `json:"total"`
}
