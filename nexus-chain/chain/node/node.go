package node

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"sync"
	"time"

	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/app"
	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/pkg/crypto"
	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/pkg/types"
	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/runtime"
	btypes "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/bank/types"
)

type Config struct {
	Home          string
	Listen        string
	BlockInterval time.Duration
	FaucetAmount  int64 // unxn per faucet claim
	FaucetEnabled bool
}

type Node struct {
	Cfg       Config
	App       *app.App
	Persister *runtime.Persister
	Treasury  *crypto.KeyPair

	mu      sync.Mutex
	mempool []btypes.MsgSend
	prevHash string
	server  *http.Server
}

func Open(cfg Config, treasury *crypto.KeyPair) (*Node, error) {
	if cfg.BlockInterval <= 0 {
		cfg.BlockInterval = 2 * time.Second
	}
	if cfg.Listen == "" {
		cfg.Listen = ":26657"
	}
	if cfg.FaucetAmount <= 0 {
		cfg.FaucetAmount = 10 * types.NXNFactor // 10 NXN
	}
	n := &Node{
		Cfg:       cfg,
		App:       app.New(),
		Persister: runtime.NewPersister(cfg.Home),
		Treasury:  treasury,
		prevHash:  "",
	}
	snap, ok, err := n.Persister.Load()
	if err != nil {
		return nil, err
	}
	if ok {
		n.App.LoadFromSnapshot(snap)
		n.prevHash = snap.AppHash
		log.Printf("loaded ledger height=%d supply=%d", snap.Height, snap.TotalSupply)
	} else {
		if err := n.App.BootstrapGenesis(treasury.Address(), -1); err != nil {
			return nil, err
		}
		if err := n.persist(); err != nil {
			return nil, err
		}
		log.Printf("genesis created treasury=%s supply_unxn=%d", treasury.Address(), app.DefaultTotalSupply)
	}
	return n, nil
}

func (n *Node) persist() error {
	return n.Persister.Save(n.App.Snapshot())
}

func (n *Node) EnqueueSend(msg btypes.MsgSend) (string, error) {
	// validate against current state without committing
	n.mu.Lock()
	defer n.mu.Unlock()
	// optimistic hash
	h := bankkeeperTxHash(msg, n.App.ChainID)
	n.mempool = append(n.mempool, msg)
	return h, nil
}

func bankkeeperTxHash(msg btypes.MsgSend, chainID string) string {
	return types.HashHex(
		[]byte(fmt.Sprintf("NEXUS/SEND|%s|%s|%s|%s|%d|%d|%s",
			chainID, msg.From, msg.To, msg.Denom, msg.Amount, msg.Sequence, msg.Memo)),
		[]byte(msg.SigHex),
	)
}

func (n *Node) ProduceBlock() error {
	n.mu.Lock()
	batch := append([]btypes.MsgSend{}, n.mempool...)
	n.mempool = nil
	n.mu.Unlock()

	recs, err := n.App.DeliverSends(batch)
	if err != nil {
		return err
	}
	txHashes := make([]string, 0, len(recs))
	for _, r := range recs {
		txHashes = append(txHashes, r.Hash)
	}

	st := n.App.Status()
	payload := fmt.Sprintf("%d|%s|%s", st.Height, st.AppHash, n.prevHash)
	sum := sha256.Sum256([]byte(payload))
	blockHash := hex.EncodeToString(sum[:])
	rec := runtime.BlockRecord{
		Height:    st.Height,
		TimeUnix:  time.Now().Unix(),
		AppHash:   st.AppHash,
		TxHashes:  txHashes,
		Proposer:  n.Treasury.Address(),
		PrevHash:  n.prevHash,
		BlockHash: blockHash,
	}
	if err := runtime.AppendBlock(n.Cfg.Home, rec); err != nil {
		return err
	}
	n.prevHash = blockHash
	return n.persist()
}

func (n *Node) Start(ctx context.Context) error {
	mux := http.NewServeMux()
	n.mountAPI(mux)
	n.server = &http.Server{Addr: n.Cfg.Listen, Handler: mux}

	go func() {
		t := time.NewTicker(n.Cfg.BlockInterval)
		defer t.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-t.C:
				if err := n.ProduceBlock(); err != nil {
					log.Printf("block error: %v", err)
				}
			}
		}
	}()

	log.Printf("NEXUS live crypto ledger RPC %s chain_id=%s", n.Cfg.Listen, n.App.ChainID)
	errCh := make(chan error, 1)
	go func() { errCh <- n.server.ListenAndServe() }()
	select {
	case <-ctx.Done():
		shutdown, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()
		_ = n.server.Shutdown(shutdown)
		return nil
	case err := <-errCh:
		if err == http.ErrServerClosed {
			return nil
		}
		return err
	}
}

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	enc := json.NewEncoder(w)
	enc.SetIndent("", "  ")
	_ = enc.Encode(v)
}
