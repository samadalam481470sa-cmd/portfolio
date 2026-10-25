package keeper

import (
	"fmt"
	"sort"

	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/pkg/types"
	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/runtime"
	assetkeeper "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/assetregistry/keeper"
	attkeeper "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/attestation/keeper"
	oraclekeeper "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/oracle/keeper"
	permkeeper "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/permissions/keeper"
	permtypes "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/permissions/types"
	stypes "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/settlement/types"
)

type Keeper struct {
	Perms   permkeeper.Keeper
	Assets  assetkeeper.Keeper
	Oracle  oraclekeeper.Keeper
	Attest  attkeeper.Keeper
	locks   map[string]string // account -> intent id (process-local for solo)
}

func New(p permkeeper.Keeper, a assetkeeper.Keeper, o oraclekeeper.Keeper, at attkeeper.Keeper) Keeper {
	return Keeper{Perms: p, Assets: a, Oracle: o, Attest: at, locks: map[string]string{}}
}

func balKey(addr, denom string) string { return "bank/bal/" + addr + "/" + denom }
func intentKey(id string) string      { return "settlement/intent/" + id }

func (k Keeper) GetBalance(ctx *runtime.Context, addr, denom string) int64 {
	raw, ok := ctx.Store.Get(balKey(addr, denom))
	if !ok {
		return 0
	}
	var v int64
	_ = runtime.FromJSON(raw, &v)
	return v
}

func (k Keeper) SetBalance(ctx *runtime.Context, addr, denom string, v int64) error {
	if v < 0 {
		return fmt.Errorf("insufficient funds")
	}
	if v >= 1<<62 {
		return fmt.Errorf("overflow")
	}
	ctx.Store.Set(balKey(addr, denom), runtime.MustJSON(v))
	return nil
}

func (k Keeper) Mint(ctx *runtime.Context, actor, to, denom string, amount int64) error {
	if err := k.Perms.Require(ctx, actor, permtypes.RoleSettlementAgent); err != nil {
		return err
	}
	if amount <= 0 {
		return fmt.Errorf("bad amount")
	}
	if denom != types.NativeDenom {
		if asset, ok := k.Assets.Get(ctx, denom); !ok || string(asset.Status) != "ACTIVE" {
			// allow mint by denom id lookup via asset id == denom for scaffold assets
			if !ok {
				return fmt.Errorf("unknown asset denom")
			}
		}
	}
	cur := k.GetBalance(ctx, to, denom)
	return k.SetBalance(ctx, to, denom, cur+amount)
}

func (k Keeper) Settle(ctx *runtime.Context, actor string, intent stypes.Intent) error {
	if ctx.IsPaused(stypes.ModuleName) {
		return fmt.Errorf("settlement paused")
	}
	if err := k.Perms.Require(ctx, actor, permtypes.RoleSettlementAgent); err != nil {
		return err
	}
	if intent.ID == "" || len(intent.Legs) == 0 {
		return fmt.Errorf("invalid intent")
	}
	if _, ok := ctx.Store.Get(intentKey(intent.ID)); ok {
		return fmt.Errorf("intent exists")
	}
	if intent.OracleFeed != "" {
		if _, err := k.Oracle.Latest(ctx, intent.OracleFeed); err != nil {
			return fmt.Errorf("oracle: %w", err)
		}
	}
	if intent.AttestationRef != "" {
		if _, ok := k.Attest.Get(ctx, intent.AttestationRef); !ok {
			return fmt.Errorf("missing attestation")
		}
	}

	// Resource locks (Solana-inspired exclusive accounts)
	locks := append([]string{}, intent.ResourceLocks...)
	sort.Strings(locks)
	for _, acct := range locks {
		if holder, ok := k.locks[acct]; ok && holder != intent.ID {
			return fmt.Errorf("account %s locked by %s", acct, holder)
		}
	}
	for _, acct := range locks {
		k.locks[acct] = intent.ID
	}
	defer func() {
		for _, acct := range locks {
			if k.locks[acct] == intent.ID {
				delete(k.locks, acct)
			}
		}
	}()

	// Apply all legs atomically or none
	type delta struct{ addr, denom string; d int64 }
	deltas := map[string]int64{}
	keyOf := func(addr, denom string) string { return addr + "|" + denom }
	for _, leg := range intent.Legs {
		if leg.Amount <= 0 {
			return fmt.Errorf("bad leg amount")
		}
		deltas[keyOf(leg.From, leg.Denom)] -= leg.Amount
		deltas[keyOf(leg.To, leg.Denom)] += leg.Amount
	}
	// check balances
	for kd, d := range deltas {
		if d >= 0 {
			continue
		}
		var addr, denom string
		for i := 0; i < len(kd); i++ {
			if kd[i] == '|' {
				addr, denom = kd[:i], kd[i+1:]
				break
			}
		}
		if k.GetBalance(ctx, addr, denom)+d < 0 {
			return fmt.Errorf("insufficient funds for %s %s", addr, denom)
		}
	}
	for kd, d := range deltas {
		var addr, denom string
		for i := 0; i < len(kd); i++ {
			if kd[i] == '|' {
				addr, denom = kd[:i], kd[i+1:]
				break
			}
		}
		cur := k.GetBalance(ctx, addr, denom)
		if err := k.SetBalance(ctx, addr, denom, cur+d); err != nil {
			return err
		}
	}
	intent.Status = "SETTLED"
	intent.SettledHeight = ctx.Height
	ctx.Store.Set(intentKey(intent.ID), runtime.MustJSON(intent))
	ctx.Emit("settlement.settled", map[string]string{"id": intent.ID})
	return nil
}
