package app

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"sort"
	"sync"

	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/pkg/types"
	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/runtime"
	assetkeeper "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/assetregistry/keeper"
	attkeeper "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/attestation/keeper"
	bankkeeper "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/bank/keeper"
	btypes "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/bank/types"
	oraclekeeper "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/oracle/keeper"
	permkeeper "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/permissions/keeper"
	permtypes "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/permissions/types"
	guardkeeper "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/protocolguard/keeper"
	settlekeeper "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/settlement/keeper"
)

// DefaultTotalSupply is 100 million NXN in unxn (6 decimals).
const DefaultTotalSupply int64 = 100_000_000 * types.NXNFactor

type App struct {
	mu          sync.Mutex
	Store       *runtime.KV
	Height      int64
	ChainID     string
	Treasury    string
	TotalSupply int64

	Perms  permkeeper.Keeper
	Assets assetkeeper.Keeper
	Attest attkeeper.Keeper
	Oracle oraclekeeper.Keeper
	Settle settlekeeper.Keeper
	Guard  guardkeeper.Keeper
	Bank   bankkeeper.Keeper

	LastAppHash string
	EventLog    []runtime.Event
	TxIndex     map[string]TxReceipt
}

type TxReceipt struct {
	Hash   string            `json:"hash"`
	Height int64             `json:"height"`
	Type   string            `json:"type"`
	OK     bool              `json:"ok"`
	Events []runtime.Event   `json:"events"`
	Raw    json.RawMessage   `json:"raw,omitempty"`
}

func New() *App {
	store := runtime.NewKV()
	perms := permkeeper.New()
	assets := assetkeeper.New(perms)
	attest := attkeeper.New(perms)
	oracle := oraclekeeper.New(perms, 1)
	settle := settlekeeper.New(perms, assets, oracle, attest)
	guard := guardkeeper.New(perms)
	bank := bankkeeper.New()
	return &App{
		Store:       store,
		Height:      0,
		ChainID:     types.ChainID,
		TotalSupply: 0,
		Perms:       perms,
		Assets:      assets,
		Attest:      attest,
		Oracle:      oracle,
		Settle:      settle,
		Guard:       guard,
		Bank:        bank,
		TxIndex:     map[string]TxReceipt{},
	}
}

func (a *App) Context() *runtime.Context {
	ctx := runtime.NewContext(a.Store, a.Height)
	a.Guard.ApplyToContext(ctx)
	return ctx
}

func (a *App) BootstrapGenesis(treasury string, supply int64) error {
	a.mu.Lock()
	defer a.mu.Unlock()
	// supply < 0 → default live crypto supply; supply == 0 → permissions only (module tests)
	if supply < 0 {
		supply = DefaultTotalSupply
	}
	ctx := runtime.NewContext(a.Store, 0)
	roles := []string{
		permtypes.RoleIssuer,
		permtypes.RoleAttestor,
		permtypes.RoleOracleReporter,
		permtypes.RoleSettlementAgent,
		permtypes.RoleGuardian,
		permtypes.RoleValidatorOps,
	}
	if err := a.Perms.Set(ctx, permtypes.Binding{Address: treasury, Roles: roles}); err != nil {
		return err
	}
	if supply > 0 {
		if err := a.Bank.GenesisMint(ctx, treasury, types.NativeDenom, supply); err != nil {
			return err
		}
	}
	a.Treasury = treasury
	a.TotalSupply = supply
	a.Height = 0
	a.LastAppHash = a.computeAppHash()
	return nil
}

func (a *App) LoadFromSnapshot(s runtime.DiskSnapshot) {
	a.mu.Lock()
	defer a.mu.Unlock()
	a.Store = runtime.NewKV()
	for k, v := range s.KV {
		a.Store.Set(k, v)
	}
	a.Height = s.Height
	a.LastAppHash = s.AppHash
	a.ChainID = s.ChainID
	if a.ChainID == "" {
		a.ChainID = types.ChainID
	}
	a.Treasury = s.Treasury
	a.TotalSupply = s.TotalSupply
}

func (a *App) Snapshot() runtime.DiskSnapshot {
	a.mu.Lock()
	defer a.mu.Unlock()
	return runtime.DiskSnapshot{
		Height:      a.Height,
		AppHash:     a.LastAppHash,
		ChainID:     a.ChainID,
		Treasury:    a.Treasury,
		TotalSupply: a.TotalSupply,
		KV:          a.Store.Snapshot(),
	}
}

func (a *App) BeginBlock() *runtime.Context {
	a.Height++
	ctx := a.Context()
	return ctx
}

func (a *App) EndBlock(ctx *runtime.Context) {
	a.EventLog = append(a.EventLog, ctx.Events...)
	a.LastAppHash = a.computeAppHash()
}

func (a *App) computeAppHash() string {
	snap := a.Store.Snapshot()
	keys := make([]string, 0, len(snap))
	for k := range snap {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	h := sha256.New()
	for _, k := range keys {
		h.Write([]byte(k))
		h.Write(snap[k])
	}
	return hex.EncodeToString(h.Sum(nil))
}

type Status struct {
	ChainID     string `json:"chain_id"`
	Height      int64  `json:"height"`
	AppHash     string `json:"app_hash"`
	Mode        string `json:"mode"`
	NativeDenom string `json:"native_denom"`
	Display     string `json:"display_asset"`
	Decimals    int    `json:"decimals"`
	TotalSupply int64  `json:"total_supply_unxn"`
	Treasury    string `json:"treasury"`
	Live        bool   `json:"live_ledger"`
	Network     string `json:"network"`
}

func (a *App) Status() Status {
	a.mu.Lock()
	defer a.mu.Unlock()
	return Status{
		ChainID:     a.ChainID,
		Height:      a.Height,
		AppHash:     a.LastAppHash,
		Mode:        "live-crypto-ledger",
		NativeDenom: types.NativeDenom,
		Display:     "NXN",
		Decimals:    6,
		TotalSupply: a.TotalSupply,
		Treasury:    a.Treasury,
		Live:        true,
		Network:     "nexus-public-testnet",
	}
}

func (a *App) WithLock(fn func() error) error {
	a.mu.Lock()
	defer a.mu.Unlock()
	return fn()
}

func (a *App) Deliver(fn func(ctx *runtime.Context) error) error {
	return a.WithLock(func() error {
		snap := a.Store.Snapshot()
		prevH := a.Height
		prevHash := a.LastAppHash
		ctx := a.BeginBlock()
		if err := fn(ctx); err != nil {
			a.Store = runtime.NewKV()
			for k, v := range snap {
				a.Store.Set(k, v)
			}
			a.Height = prevH
			a.LastAppHash = prevHash
			return fmt.Errorf("deliver: %w", err)
		}
		a.EndBlock(ctx)
		return nil
	})
}

// DeliverSend applies a signed NXN transfer in a new block (or fails atomically).
func (a *App) DeliverSend(msg btypes.MsgSend) (TxReceipt, error) {
	recs, err := a.DeliverSends([]btypes.MsgSend{msg})
	if err != nil {
		return TxReceipt{}, err
	}
	if len(recs) == 0 {
		return TxReceipt{}, fmt.Errorf("tx not included")
	}
	return recs[0], nil
}

// DeliverSends applies transfers in a single block; invalid txs are skipped.
func (a *App) DeliverSends(msgs []btypes.MsgSend) ([]TxReceipt, error) {
	var out []TxReceipt
	err := a.WithLock(func() error {
		ctx := a.BeginBlock()
		for _, msg := range msgs {
			evBefore := len(ctx.Events)
			hash, err := a.Bank.Send(ctx, msg, a.ChainID)
			if err != nil {
				// drop failed tx; keep block progressing
				ctx.Events = ctx.Events[:evBefore]
				continue
			}
			raw, _ := json.Marshal(msg)
			evs := append([]runtime.Event{}, ctx.Events[evBefore:]...)
			rec := TxReceipt{
				Hash: hash, Height: a.Height, Type: "bank.send", OK: true,
				Events: evs, Raw: raw,
			}
			a.TxIndex[hash] = rec
			out = append(out, rec)
		}
		a.EndBlock(ctx)
		return nil
	})
	return out, err
}

func (a *App) GetTx(hash string) (TxReceipt, bool) {
	a.mu.Lock()
	defer a.mu.Unlock()
	r, ok := a.TxIndex[hash]
	return r, ok
}

func (a *App) Balance(addr, denom string) int64 {
	a.mu.Lock()
	defer a.mu.Unlock()
	if denom == "" {
		denom = types.NativeDenom
	}
	return a.Bank.GetBalance(a.Context(), addr, denom)
}

func (a *App) AccountSequence(addr string) uint64 {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.Bank.GetAccount(a.Context(), addr).Sequence
}
