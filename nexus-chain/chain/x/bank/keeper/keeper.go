package keeper

import (
	"encoding/hex"
	"fmt"

	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/pkg/crypto"
	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/pkg/types"
	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/runtime"
	btypes "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/bank/types"
)

type Keeper struct{}

func New() Keeper { return Keeper{} }

func balKey(addr, denom string) string  { return "bank/bal/" + addr + "/" + denom }
func acctKey(addr string) string        { return "bank/acct/" + addr }
func supplyKey(denom string) string     { return "bank/supply/" + denom }
func txSeenKey(txHash string) string    { return "bank/seen/" + txHash }

func (k Keeper) GetBalance(ctx *runtime.Context, addr, denom string) int64 {
	raw, ok := ctx.Store.Get(balKey(addr, denom))
	if !ok {
		return 0
	}
	var v int64
	_ = runtime.FromJSON(raw, &v)
	return v
}

func (k Keeper) setBalance(ctx *runtime.Context, addr, denom string, v int64) error {
	if v < 0 {
		return fmt.Errorf("insufficient funds")
	}
	if v >= 1<<62 {
		return fmt.Errorf("overflow")
	}
	ctx.Store.Set(balKey(addr, denom), runtime.MustJSON(v))
	return nil
}

func (k Keeper) GetAccount(ctx *runtime.Context, addr string) btypes.AccountMeta {
	raw, ok := ctx.Store.Get(acctKey(addr))
	if !ok {
		return btypes.AccountMeta{Address: addr, Sequence: 0}
	}
	var a btypes.AccountMeta
	_ = runtime.FromJSON(raw, &a)
	return a
}

func (k Keeper) setAccount(ctx *runtime.Context, a btypes.AccountMeta) {
	ctx.Store.Set(acctKey(a.Address), runtime.MustJSON(a))
}

func (k Keeper) GetSupply(ctx *runtime.Context, denom string) int64 {
	raw, ok := ctx.Store.Get(supplyKey(denom))
	if !ok {
		return 0
	}
	var v int64
	_ = runtime.FromJSON(raw, &v)
	return v
}

func (k Keeper) setSupply(ctx *runtime.Context, denom string, v int64) {
	ctx.Store.Set(supplyKey(denom), runtime.MustJSON(v))
}

// GenesisMint creates initial circulating supply (genesis / treasury only).
func (k Keeper) GenesisMint(ctx *runtime.Context, to, denom string, amount int64) error {
	if amount <= 0 {
		return fmt.Errorf("bad amount")
	}
	if err := k.setBalance(ctx, to, denom, k.GetBalance(ctx, to, denom)+amount); err != nil {
		return err
	}
	k.setSupply(ctx, denom, k.GetSupply(ctx, denom)+amount)
	ctx.Emit("bank.mint", map[string]string{"to": to, "denom": denom, "amount": fmt.Sprintf("%d", amount)})
	return nil
}

func SignBytes(msg btypes.MsgSend, chainID string) []byte {
	return []byte(fmt.Sprintf(
		"NEXUS/SEND|%s|%s|%s|%s|%d|%d|%s",
		chainID, msg.From, msg.To, msg.Denom, msg.Amount, msg.Sequence, msg.Memo,
	))
}

func TxHash(msg btypes.MsgSend, chainID string) string {
	return types.HashHex(SignBytes(msg, chainID), []byte(msg.SigHex))
}

func (k Keeper) Send(ctx *runtime.Context, msg btypes.MsgSend, chainID string) (string, error) {
	if ctx.IsPaused(btypes.ModuleName) {
		return "", fmt.Errorf("bank paused")
	}
	if msg.Denom == "" {
		msg.Denom = types.NativeDenom
	}
	if msg.Amount <= 0 {
		return "", fmt.Errorf("amount must be positive")
	}
	if msg.From == "" || msg.To == "" || msg.From == msg.To {
		return "", fmt.Errorf("invalid from/to")
	}
	pub, err := crypto.ParsePub(msg.PubKeyHex)
	if err != nil {
		return "", err
	}
	if crypto.AddressFromPub(pub) != msg.From {
		return "", fmt.Errorf("pubkey does not match from address")
	}
	sig, err := hex.DecodeString(msg.SigHex)
	if err != nil {
		return "", err
	}
	if !crypto.Verify(pub, SignBytes(msg, chainID), sig) {
		return "", fmt.Errorf("invalid signature")
	}
	acct := k.GetAccount(ctx, msg.From)
	if msg.Sequence != acct.Sequence {
		return "", fmt.Errorf("bad sequence: got %d want %d", msg.Sequence, acct.Sequence)
	}
	txHash := TxHash(msg, chainID)
	if _, ok := ctx.Store.Get(txSeenKey(txHash)); ok {
		return "", fmt.Errorf("duplicate tx")
	}
	fromBal := k.GetBalance(ctx, msg.From, msg.Denom)
	if fromBal < msg.Amount {
		return "", fmt.Errorf("insufficient funds")
	}
	if err := k.setBalance(ctx, msg.From, msg.Denom, fromBal-msg.Amount); err != nil {
		return "", err
	}
	if err := k.setBalance(ctx, msg.To, msg.Denom, k.GetBalance(ctx, msg.To, msg.Denom)+msg.Amount); err != nil {
		return "", err
	}
	acct.Sequence++
	acct.PubKey = msg.PubKeyHex
	k.setAccount(ctx, acct)
	ctx.Store.Set(txSeenKey(txHash), []byte{1})
	ctx.Emit("bank.send", map[string]string{
		"tx_hash": txHash,
		"from":    msg.From,
		"to":      msg.To,
		"denom":   msg.Denom,
		"amount":  fmt.Sprintf("%d", msg.Amount),
	})
	return txHash, nil
}
