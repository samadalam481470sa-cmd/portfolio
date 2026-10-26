package types

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
)

const (
	ChainID     = "nexus-1"
	NativeDenom = "unxn"
	NXNFactor   = 1_000_000
)

type Address string

func (a Address) String() string { return string(a) }

func HashHex(parts ...[]byte) string {
	h := sha256.New()
	for _, p := range parts {
		h.Write(p)
	}
	return hex.EncodeToString(h.Sum(nil))
}

func MustAmount(v int64) int64 {
	if v < 0 {
		panic(fmt.Sprintf("negative amount %d", v))
	}
	return v
}
