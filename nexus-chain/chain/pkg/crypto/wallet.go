package crypto

import (
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

// AddressFromPub returns a stable nexus... address from an Ed25519 public key.
func AddressFromPub(pub ed25519.PublicKey) string {
	sum := sha256.Sum256(pub)
	return "nexus" + hex.EncodeToString(sum[:20])
}

func (k *KeyPair) Address() string {
	return AddressFromPub(k.Public)
}

type WalletFile struct {
	Address    string `json:"address"`
	PublicKey  string `json:"public_key"`
	PrivateKey string `json:"private_key"`
	CreatedAt  int64  `json:"created_at_unix"`
	Network    string `json:"network"`
}

func SaveWallet(path string, kp *KeyPair, network string, createdAt int64) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	wf := WalletFile{
		Address:    kp.Address(),
		PublicKey:  hex.EncodeToString(kp.Public),
		PrivateKey: hex.EncodeToString(kp.Private),
		CreatedAt:  createdAt,
		Network:    network,
	}
	b, err := json.MarshalIndent(wf, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, b, 0o600)
}

func LoadWallet(path string) (*KeyPair, *WalletFile, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, nil, err
	}
	var wf WalletFile
	if err := json.Unmarshal(b, &wf); err != nil {
		return nil, nil, err
	}
	priv, err := hex.DecodeString(wf.PrivateKey)
	if err != nil || len(priv) != ed25519.PrivateKeySize {
		return nil, nil, fmt.Errorf("bad private key")
	}
	pub := ed25519.PrivateKey(priv).Public().(ed25519.PublicKey)
	kp := &KeyPair{Private: ed25519.PrivateKey(priv), Public: pub}
	if kp.Address() != wf.Address {
		return nil, nil, fmt.Errorf("address mismatch")
	}
	return kp, &wf, nil
}
