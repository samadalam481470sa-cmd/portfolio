package runtime

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sync"
)

type DiskSnapshot struct {
	Height      int64             `json:"height"`
	AppHash     string            `json:"app_hash"`
	ChainID     string            `json:"chain_id"`
	Treasury    string            `json:"treasury"`
	TotalSupply int64             `json:"total_supply_unxn"`
	KV          map[string][]byte `json:"kv"`
}

type Persister struct {
	mu   sync.Mutex
	path string
}

func NewPersister(home string) *Persister {
	return &Persister{path: filepath.Join(home, "state", "ledger.json")}
}

func (p *Persister) Save(s DiskSnapshot) error {
	p.mu.Lock()
	defer p.mu.Unlock()
	if err := os.MkdirAll(filepath.Dir(p.path), 0o755); err != nil {
		return err
	}
	tmp := p.path + ".tmp"
	b, err := json.MarshalIndent(s, "", "  ")
	if err != nil {
		return err
	}
	if err := os.WriteFile(tmp, b, 0o600); err != nil {
		return err
	}
	return os.Rename(tmp, p.path)
}

func (p *Persister) Load() (DiskSnapshot, bool, error) {
	p.mu.Lock()
	defer p.mu.Unlock()
	b, err := os.ReadFile(p.path)
	if err != nil {
		if os.IsNotExist(err) {
			return DiskSnapshot{}, false, nil
		}
		return DiskSnapshot{}, false, err
	}
	var s DiskSnapshot
	if err := json.Unmarshal(b, &s); err != nil {
		return DiskSnapshot{}, false, err
	}
	if s.KV == nil {
		s.KV = map[string][]byte{}
	}
	return s, true, nil
}

type BlockRecord struct {
	Height    int64    `json:"height"`
	TimeUnix  int64    `json:"time_unix"`
	AppHash   string   `json:"app_hash"`
	TxHashes  []string `json:"tx_hashes"`
	Proposer  string   `json:"proposer"`
	PrevHash  string   `json:"prev_hash"`
	BlockHash string   `json:"block_hash"`
}

func AppendBlock(home string, b BlockRecord) error {
	dir := filepath.Join(home, "blocks")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	path := filepath.Join(dir, fmt.Sprintf("%020d.json", b.Height))
	raw, err := json.MarshalIndent(b, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, raw, 0o644)
}

func LoadBlock(home string, height int64) (BlockRecord, error) {
	path := filepath.Join(home, "blocks", fmt.Sprintf("%020d.json", height))
	b, err := os.ReadFile(path)
	if err != nil {
		return BlockRecord{}, err
	}
	var rec BlockRecord
	return rec, json.Unmarshal(b, &rec)
}
