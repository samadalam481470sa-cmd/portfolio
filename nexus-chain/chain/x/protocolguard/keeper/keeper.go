package keeper

import (
	"fmt"

	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/runtime"
	permkeeper "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/permissions/keeper"
	permtypes "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/permissions/types"
	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/protocolguard/types"
)

type Keeper struct {
	Perms permkeeper.Keeper
}

func New(perms permkeeper.Keeper) Keeper { return Keeper{Perms: perms} }

const stateKey = "protocolguard/state"

func (k Keeper) Get(ctx *runtime.Context) types.GuardState {
	raw, ok := ctx.Store.Get(stateKey)
	if !ok {
		return types.GuardState{PausedModules: map[string]bool{}}
	}
	var s types.GuardState
	_ = runtime.FromJSON(raw, &s)
	if s.PausedModules == nil {
		s.PausedModules = map[string]bool{}
	}
	return s
}

func (k Keeper) ApplyToContext(ctx *runtime.Context) {
	s := k.Get(ctx)
	ctx.Paused = s.PausedModules
}

func (k Keeper) SetPaused(ctx *runtime.Context, actor, module string, paused bool) error {
	if err := k.Perms.Require(ctx, actor, permtypes.RoleGuardian); err != nil {
		return err
	}
	if module == types.ModuleName {
		return fmt.Errorf("cannot pause protocolguard itself via this path")
	}
	s := k.Get(ctx)
	s.PausedModules[module] = paused
	s.UpdatedHeight = ctx.Height
	s.UpdatedBy = actor
	ctx.Store.Set(stateKey, runtime.MustJSON(s))
	ctx.Paused = s.PausedModules
	ctx.Emit("protocolguard.pause", map[string]string{"module": module, "paused": fmt.Sprintf("%v", paused)})
	return nil
}
