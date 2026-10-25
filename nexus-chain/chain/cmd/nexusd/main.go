package main

import (
	"bytes"
	"context"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"strconv"
	"syscall"
	"time"

	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/node"
	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/pkg/crypto"
	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/pkg/types"
	bankkeeper "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/bank/keeper"
	btypes "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/bank/types"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintf(os.Stderr, `NEXUS live crypto ledger

Usage:
  nexusd start [--home DIR] [--listen ADDR] [--faucet]
  nexusd wallet create [--out FILE]
  nexusd tx send --from WALLET.json --to ADDR --amount NXN [--rpc URL]
  nexusd balance --address ADDR [--rpc URL]
  nexusd version
`)
		os.Exit(2)
	}
	switch os.Args[1] {
	case "version":
		fmt.Println("nexusd 0.2.0-live-crypto (NXN public testnet ledger)")
	case "wallet":
		cmdWallet(os.Args[2:])
	case "tx":
		cmdTx(os.Args[2:])
	case "balance":
		cmdBalance(os.Args[2:])
	case "start", "solo":
		cmdStart(os.Args[2:])
	default:
		log.Fatalf("unknown command %s", os.Args[1])
	}
}

func cmdStart(args []string) {
	fs := flag.NewFlagSet("start", flag.ExitOnError)
	home := fs.String("home", filepath.Join(os.TempDir(), "nexus-live"), "data directory")
	listen := fs.String("listen", ":26657", "RPC listen address")
	faucet := fs.Bool("faucet", true, "enable testnet faucet")
	interval := fs.Duration("block-interval", 2*time.Second, "block time")
	_ = fs.Parse(args)

	_ = os.MkdirAll(*home, 0o755)
	treasuryPath := filepath.Join(*home, "keys", "treasury.json")
	var treasury *crypto.KeyPair
	if _, err := os.Stat(treasuryPath); err == nil {
		kp, _, err := crypto.LoadWallet(treasuryPath)
		if err != nil {
			log.Fatal(err)
		}
		treasury = kp
	} else {
		kp, err := crypto.Generate()
		if err != nil {
			log.Fatal(err)
		}
		if err := crypto.SaveWallet(treasuryPath, kp, "nexus-public-testnet", time.Now().Unix()); err != nil {
			log.Fatal(err)
		}
		treasury = kp
		fmt.Println("treasury wallet:", treasury.Address())
		fmt.Println("saved:", treasuryPath)
	}

	n, err := node.Open(node.Config{
		Home: *home, Listen: *listen, BlockInterval: *interval,
		FaucetEnabled: *faucet, FaucetAmount: 10 * types.NXNFactor,
	}, treasury)
	if err != nil {
		log.Fatal(err)
	}

	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()
	fmt.Printf("NXN live ledger: http://127.0.0.1%s/\n", *listen)
	fmt.Printf("RPC status:     http://127.0.0.1%s/v1/status\n", *listen)
	if err := n.Start(ctx); err != nil {
		log.Fatal(err)
	}
}

func cmdWallet(args []string) {
	if len(args) < 1 || args[0] != "create" {
		log.Fatal("usage: nexusd wallet create [--out FILE]")
	}
	fs := flag.NewFlagSet("wallet-create", flag.ExitOnError)
	out := fs.String("out", "wallet.json", "output wallet file")
	_ = fs.Parse(args[1:])
	kp, err := crypto.Generate()
	if err != nil {
		log.Fatal(err)
	}
	if err := crypto.SaveWallet(*out, kp, "nexus-public-testnet", time.Now().Unix()); err != nil {
		log.Fatal(err)
	}
	fmt.Println("address:", kp.Address())
	fmt.Println("wrote:", *out)
}

func cmdTx(args []string) {
	if len(args) < 1 || args[0] != "send" {
		log.Fatal("usage: nexusd tx send --from wallet.json --to ADDR --amount 1.5")
	}
	fs := flag.NewFlagSet("tx-send", flag.ExitOnError)
	from := fs.String("from", "", "wallet json")
	to := fs.String("to", "", "recipient nexus address")
	amount := fs.String("amount", "", "amount in NXN (e.g. 1.5)")
	rpc := fs.String("rpc", "http://127.0.0.1:26657", "node RPC")
	memo := fs.String("memo", "", "memo")
	_ = fs.Parse(args[1:])
	if *from == "" || *to == "" || *amount == "" {
		log.Fatal("--from --to --amount required")
	}
	kp, _, err := crypto.LoadWallet(*from)
	if err != nil {
		log.Fatal(err)
	}
	unxn, err := parseNXN(*amount)
	if err != nil {
		log.Fatal(err)
	}
	seqResp, err := http.Get(*rpc + "/v1/account?address=" + kp.Address())
	if err != nil {
		log.Fatal(err)
	}
	defer seqResp.Body.Close()
	var acct struct {
		Sequence uint64 `json:"sequence"`
	}
	_ = json.NewDecoder(seqResp.Body).Decode(&acct)
	msg := btypes.MsgSend{
		From: kp.Address(), To: *to, Denom: types.NativeDenom,
		Amount: unxn, Sequence: acct.Sequence, Memo: *memo,
		PubKeyHex: hex.EncodeToString(kp.Public),
	}
	sig := crypto.Sign(kp.Private, bankkeeper.SignBytes(msg, types.ChainID))
	msg.SigHex = hex.EncodeToString(sig)
	body, _ := json.Marshal(msg)
	resp, err := http.Post(*rpc+"/v1/tx/send", "application/json", bytes.NewReader(body))
	if err != nil {
		log.Fatal(err)
	}
	defer resp.Body.Close()
	_, _ = io.Copy(os.Stdout, resp.Body)
	fmt.Println()
}

func cmdBalance(args []string) {
	fs := flag.NewFlagSet("balance", flag.ExitOnError)
	addr := fs.String("address", "", "address")
	rpc := fs.String("rpc", "http://127.0.0.1:26657", "rpc")
	_ = fs.Parse(args)
	resp, err := http.Get(*rpc + "/v1/balance?address=" + *addr)
	if err != nil {
		log.Fatal(err)
	}
	defer resp.Body.Close()
	_, _ = io.Copy(os.Stdout, resp.Body)
	fmt.Println()
}

func parseNXN(s string) (int64, error) {
	// support integer NXN or decimal with up to 6 places without float
	neg := false
	if len(s) > 0 && s[0] == '-' {
		return 0, fmt.Errorf("negative")
	}
	whole := s
	frac := ""
	if i := indexByte(s, '.'); i >= 0 {
		whole, frac = s[:i], s[i+1:]
	}
	if whole == "" {
		whole = "0"
	}
	w, err := strconv.ParseInt(whole, 10, 64)
	if err != nil {
		return 0, err
	}
	if len(frac) > 6 {
		return 0, fmt.Errorf("too many decimals")
	}
	for len(frac) < 6 {
		frac += "0"
	}
	f, err := strconv.ParseInt(frac, 10, 64)
	if err != nil {
		return 0, err
	}
	if neg {
		return 0, fmt.Errorf("negative")
	}
	return w*types.NXNFactor + f, nil
}

func indexByte(s string, c byte) int {
	for i := 0; i < len(s); i++ {
		if s[i] == c {
			return i
		}
	}
	return -1
}
