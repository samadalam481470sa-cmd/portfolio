package main

import (
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"time"

	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/app"
	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/pkg/crypto"
	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/pkg/types"
	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/runtime"
	assettypes "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/assetregistry/types"
	atttypes "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/attestation/types"
	oracletypes "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/oracle/types"
	settletypes "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/settlement/types"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintf(os.Stderr, "usage: nexusd <solo|version|init>\n")
		os.Exit(2)
	}
	switch os.Args[1] {
	case "version":
		fmt.Println("nexusd 0.1.0-testnet scaffold (Cosmos/CometBFT integration per BLUEPRINT)")
	case "init":
		home := flagHome(os.Args[2:])
		if err := os.MkdirAll(home, 0o755); err != nil {
			log.Fatal(err)
		}
		fmt.Println("initialized", home)
	case "solo":
		runSolo(flagHome(os.Args[2:]))
	default:
		log.Fatalf("unknown command %s", os.Args[1])
	}
}

func flagHome(args []string) string {
	fs := flag.NewFlagSet("nexusd", flag.ExitOnError)
	home := fs.String("home", filepath.Join(os.TempDir(), "nexus-home"), "home directory")
	_ = fs.Parse(args)
	return *home
}

func runSolo(home string) {
	_ = os.MkdirAll(home, 0o755)
	a := app.New()
	adminKP, err := crypto.Generate()
	if err != nil {
		log.Fatal(err)
	}
	admin := adminKP.Address()
	if err := a.BootstrapGenesis(admin); err != nil {
		log.Fatal(err)
	}
	// persist admin key for local demo
	_ = os.WriteFile(filepath.Join(home, "admin.addr"), []byte(admin), 0o600)
	_ = os.WriteFile(filepath.Join(home, "admin.pub"), []byte(hex.EncodeToString(adminKP.Public)), 0o600)

	mux := http.NewServeMux()
	mux.HandleFunc("/v1/status", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, a.Status())
	})
	mux.HandleFunc("/v1/admin", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, map[string]string{"admin": admin})
	})
	mux.HandleFunc("/v1/demo/bootstrap-finance", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "POST only", 405)
			return
		}
		err := a.Deliver(func(ctx *runtime.Context) error {
			if err := a.Assets.Register(ctx, admin, assettypes.Asset{
				ID: "cash-usd", Denom: "ucash", DisplayName: "Synthetic Cash", Decimals: 6, AssetClass: "FIAT_SYNTH",
			}); err != nil {
				return err
			}
			if err := a.Settle.Mint(ctx, admin, admin, types.NativeDenom, 1_000_000_000); err != nil {
				return err
			}
			if err := a.Oracle.Submit(ctx, admin, oracletypes.Report{
				ID: "rep-1", FeedID: "NXN-USD", Value: "1.00", Decimals: 2,
				TimestampUnix: time.Now().Unix(), ExpiresHeight: ctx.Height + 100,
			}); err != nil {
				return err
			}
			payloadHash := types.HashHex([]byte(`{"synthetic":true}`))
			msg := []byte("att-1|acct:demo|fin.v1|" + payloadHash)
			sig := crypto.Sign(adminKP.Private, msg)
			return a.Attest.Anchor(ctx, atttypes.Attestation{
				ID: "att-1", SubjectRef: "acct:demo", SchemaID: "fin.v1",
				PayloadHash: payloadHash, Signer: admin,
				SignatureHex: hex.EncodeToString(sig), PubKeyHex: hex.EncodeToString(adminKP.Public),
				ObservedAtUnix: time.Now().Unix(),
			})
		})
		if err != nil {
			http.Error(w, err.Error(), 400)
			return
		}
		writeJSON(w, a.Status())
	})
	mux.HandleFunc("/v1/demo/settle", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "POST only", 405)
			return
		}
		to := r.URL.Query().Get("to")
		if to == "" {
			to = "nexusreceiver0001"
		}
		err := a.Deliver(func(ctx *runtime.Context) error {
			return a.Settle.Settle(ctx, admin, settletypes.Intent{
				ID: fmt.Sprintf("intent-%d", ctx.Height),
				Legs: []settletypes.Leg{{
					From: admin, To: to, Denom: types.NativeDenom, Amount: 1_000_000,
				}},
				OracleFeed:     "NXN-USD",
				AttestationRef: "att-1",
				ResourceLocks:  []string{admin, to},
			})
		})
		if err != nil {
			http.Error(w, err.Error(), 400)
			return
		}
		bal := a.Settle.GetBalance(a.Context(), to, types.NativeDenom)
		writeJSON(w, map[string]any{"status": a.Status(), "receiver_balance_unxn": bal})
	})
	mux.HandleFunc("/v1/balance", func(w http.ResponseWriter, r *http.Request) {
		addr := r.URL.Query().Get("address")
		denom := r.URL.Query().Get("denom")
		if denom == "" {
			denom = types.NativeDenom
		}
		writeJSON(w, map[string]any{
			"address": addr,
			"denom":   denom,
			"amount":  a.Settle.GetBalance(a.Context(), addr, denom),
		})
	})

	addr := ":26657"
	log.Printf("NEXUS solo RPC on %s (home=%s admin=%s)", addr, home, admin)
	log.Fatal(http.ListenAndServe(addr, mux))
}

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	enc := json.NewEncoder(w)
	enc.SetIndent("", "  ")
	_ = enc.Encode(v)
}
