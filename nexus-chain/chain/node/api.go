package node

import (
	"encoding/hex"
	"encoding/json"
	"net/http"
	"strconv"
	"sync"
	"time"

	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/pkg/crypto"
	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/pkg/types"
	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/runtime"
	btypes "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/bank/types"
	bankkeeper "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/bank/keeper"
)

var faucetMu sync.Mutex
var faucetSeen = map[string]int64{}

func (n *Node) mountAPI(mux *http.ServeMux) {
	mux.HandleFunc("/v1/status", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, n.App.Status())
	})
	mux.HandleFunc("/v1/supply", func(w http.ResponseWriter, r *http.Request) {
		st := n.App.Status()
		writeJSON(w, map[string]any{
			"denom":             types.NativeDenom,
			"display":           "NXN",
			"decimals":          6,
			"total_supply_unxn": st.TotalSupply,
			"total_supply_nxn":  float64(st.TotalSupply) / float64(types.NXNFactor),
		})
	})
	mux.HandleFunc("/v1/balance", func(w http.ResponseWriter, r *http.Request) {
		addr := r.URL.Query().Get("address")
		denom := r.URL.Query().Get("denom")
		if denom == "" {
			denom = types.NativeDenom
		}
		bal := n.App.Balance(addr, denom)
		writeJSON(w, map[string]any{
			"address": addr, "denom": denom, "amount_unxn": bal,
			"amount_nxn": float64(bal) / float64(types.NXNFactor),
			"sequence":   n.App.AccountSequence(addr),
		})
	})
	mux.HandleFunc("/v1/account", func(w http.ResponseWriter, r *http.Request) {
		addr := r.URL.Query().Get("address")
		writeJSON(w, map[string]any{
			"address":  addr,
			"sequence": n.App.AccountSequence(addr),
			"balances": map[string]int64{
				types.NativeDenom: n.App.Balance(addr, types.NativeDenom),
			},
		})
	})
	mux.HandleFunc("/v1/tx/send", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "POST only", 405)
			return
		}
		var msg btypes.MsgSend
		if err := json.NewDecoder(r.Body).Decode(&msg); err != nil {
			http.Error(w, err.Error(), 400)
			return
		}
		if msg.Denom == "" {
			msg.Denom = types.NativeDenom
		}
		h, err := n.EnqueueSend(msg)
		if err != nil {
			http.Error(w, err.Error(), 400)
			return
		}
		writeJSON(w, map[string]any{"tx_hash": h, "status": "pending", "note": "included in next block"})
	})
	mux.HandleFunc("/v1/tx/", func(w http.ResponseWriter, r *http.Request) {
		hash := r.URL.Path[len("/v1/tx/"):]
		if rec, ok := n.App.GetTx(hash); ok {
			writeJSON(w, rec)
			return
		}
		http.Error(w, "not found (pending or unknown)", 404)
	})
	mux.HandleFunc("/v1/blocks/latest", func(w http.ResponseWriter, r *http.Request) {
		h := n.App.Status().Height
		if h < 1 {
			http.Error(w, "no blocks", 404)
			return
		}
		rec, err := runtime.LoadBlock(n.Cfg.Home, h)
		if err != nil {
			http.Error(w, err.Error(), 404)
			return
		}
		writeJSON(w, rec)
	})
	mux.HandleFunc("/v1/blocks/", func(w http.ResponseWriter, r *http.Request) {
		hs := r.URL.Path[len("/v1/blocks/"):]
		height, err := strconv.ParseInt(hs, 10, 64)
		if err != nil {
			http.Error(w, "bad height", 400)
			return
		}
		rec, err := runtime.LoadBlock(n.Cfg.Home, height)
		if err != nil {
			http.Error(w, "not found", 404)
			return
		}
		writeJSON(w, rec)
	})
	mux.HandleFunc("/v1/faucet", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "POST only", 405)
			return
		}
		if !n.Cfg.FaucetEnabled {
			http.Error(w, "faucet disabled", 403)
			return
		}
		var body struct {
			Address string `json:"address"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil || body.Address == "" {
			http.Error(w, "address required", 400)
			return
		}
		faucetMu.Lock()
		last := faucetSeen[body.Address]
		if time.Now().Unix()-last < 60 {
			faucetMu.Unlock()
			http.Error(w, "rate limited (60s)", 429)
			return
		}
		faucetSeen[body.Address] = time.Now().Unix()
		faucetMu.Unlock()

		seq := n.App.AccountSequence(n.Treasury.Address())
		msg := btypes.MsgSend{
			From: n.Treasury.Address(), To: body.Address,
			Denom: types.NativeDenom, Amount: n.Cfg.FaucetAmount,
			Sequence: seq, Memo: "faucet",
			PubKeyHex: hex.EncodeToString(n.Treasury.Public),
		}
		sig := crypto.Sign(n.Treasury.Private, bankkeeper.SignBytes(msg, n.App.ChainID))
		msg.SigHex = hex.EncodeToString(sig)
		h, err := n.EnqueueSend(msg)
		if err != nil {
			http.Error(w, err.Error(), 400)
			return
		}
		writeJSON(w, map[string]any{
			"tx_hash": h, "amount_unxn": n.Cfg.FaucetAmount,
			"amount_nxn": float64(n.Cfg.FaucetAmount) / float64(types.NXNFactor),
			"to":         body.Address,
		})
	})
	mux.HandleFunc("/v1/wallet/create", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "POST only", 405)
			return
		}
		kp, err := crypto.Generate()
		if err != nil {
			http.Error(w, err.Error(), 500)
			return
		}
		writeJSON(w, map[string]any{
			"address":     kp.Address(),
			"public_key":  hex.EncodeToString(kp.Public),
			"private_key": hex.EncodeToString(kp.Private),
			"network":     "nexus-public-testnet",
			"warning":     "Store private_key securely. Anyone with it can spend your NXN.",
		})
	})
	mux.HandleFunc("/", n.serveExplorer)
	mux.HandleFunc("/explorer", n.serveExplorer)
}

func (n *Node) serveExplorer(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/" && r.URL.Path != "/explorer" {
		http.NotFound(w, r)
		return
	}
	st := n.App.Status()
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	_, _ = w.Write([]byte(renderExplorer(st.ChainID, st.Height, st.AppHash, st.TotalSupply, st.Treasury)))
}
