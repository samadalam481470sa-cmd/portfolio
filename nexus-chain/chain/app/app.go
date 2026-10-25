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
	oraclekeeper "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/oracle/keeper"
	permkeeper "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/permissions/keeper"
	permtypes "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/permissions/types"
	guardkeeper "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/protocolguard/keeper"
	settlekeeper "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/settlement/keeper"
)

// App is the NEXUS application state machine.
// Solo mode uses an in-process store. Production wires the same module keepers
// into a Cosmos SDK app with CometBFT consensus (see docs/BLUEPRINT.md §8).
type App struct {
	mu     sync.Mutex
	Store  *runtime.KV
	Height int64
	ChainID string

	Perms    permkeeper.Keeper
	Assets   assetkeeper.Keeper
	Attest   attkeeper.Keeper
	Oracle   oraclekeeper.Keeper
	Settle   settlekeeper.Keeper
	Guard    guardkeeper.Keeper

	LastAppHash string
	EventLog    []runtime.Event
}

func New() *App {
	store := runtime.NewKV()
	perms := permkeeper.New()
	assets := assetkeeper.New(perms)
	attest := attkeeper.New(perms)
	oracle := oraclekeeper.New(perms, 1)
	settle := settlekeeper.New(perms, assets, oracle, attest)
	guard := guardkeeper.New(perms)
	return &App{
		Store:   store,
		Height:  0,
		ChainID: types.ChainID,
		Perms:   perms,
		Assets:  assets,
		Attest:  attest,
		Oracle:  oracle,
		Settle:  settle,
		Guard:   guard,
	}
}

func (a *App) Context() *runtime.Context {
	ctx := runtime.NewContext(a.Store, a.Height)
	a.Guard.ApplyToContext(ctx)
	return ctx
}

func (a *App) BootstrapGenesis(admin string) error {
	a.mu.Lock()
	defer a.mu.Unlock()
	ctx := runtime.NewContext(a.Store, 0)
	roles := []string{
		permtypes.RoleIssuer,
		permtypes.RoleAttestor,
		permtypes.RoleOracleReporter,
		permtypes.RoleSettlementAgent,
		permtypes.RoleGuardian,
		permtypes.RoleValidatorOps,
	}
	if err := a.Perms.Set(ctx, permtypes.Binding{Address: admin, Roles: roles}); err != nil {
		return err
	}
	a.Height = 0
	a.LastAppHash = a.computeAppHash()
	return nil
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
	ChainID  string `json:"chain_id"`
	Height   int64  `json:"height"`
	AppHash  string `json:"app_hash"`
	Mode     string `json:"mode"`
	Native   string `json:"native_denom"`
}

func (a *App) Status() Status {
	a.mu.Lock()
	defer a.mu.Unlock()
	return Status{
		ChainID: a.ChainID,
		Height:  a.Height,
		AppHash: a.LastAppHash,
		Mode:    "solo-scaffold",
		Native:  types.NativeDenom,
	}
}

func (a *App) ExportGenesisJSON() ([]byte, error) {
	a.mu.Lock()
	defer a.mu.Unlock()
	payload := map[string]any{
		"chain_id": a.ChainID,
		"height":   a.Height,
		"app_hash": a.LastAppHash,
		"note":     "Scaffold genesis export; production uses Cosmos SDK genesis.",
	}
	return json.MarshalIndent(payload, "", "  ")
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
			// restore store + height on failed delivery
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
