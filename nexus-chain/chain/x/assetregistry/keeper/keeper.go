package keeper

import (
	"fmt"

	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/runtime"
	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/assetregistry/types"
	permkeeper "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/permissions/keeper"
	permtypes "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/permissions/types"
)

type Keeper struct {
	Perms permkeeper.Keeper
}

func New(perms permkeeper.Keeper) Keeper { return Keeper{Perms: perms} }

func assetKey(id string) string  { return "assetregistry/id/" + id }
func denomKey(d string) string   { return "assetregistry/denom/" + d }

func (k Keeper) Register(ctx *runtime.Context, actor string, a types.Asset) error {
	if ctx.IsPaused(types.ModuleName) {
		return fmt.Errorf("assetregistry paused")
	}
	if err := k.Perms.Require(ctx, actor, permtypes.RoleIssuer); err != nil {
		return err
	}
	if a.ID == "" || a.Denom == "" {
		return fmt.Errorf("id and denom required")
	}
	if _, ok := ctx.Store.Get(assetKey(a.ID)); ok {
		return fmt.Errorf("asset id exists")
	}
	if _, ok := ctx.Store.Get(denomKey(a.Denom)); ok {
		return fmt.Errorf("denom exists")
	}
	a.Issuer = actor
	a.Status = types.StatusActive
	a.CreatedHeight = ctx.Height
	ctx.Store.Set(assetKey(a.ID), runtime.MustJSON(a))
	ctx.Store.Set(denomKey(a.Denom), []byte(a.ID))
	ctx.Emit("asset.registered", map[string]string{"id": a.ID, "denom": a.Denom})
	return nil
}

func (k Keeper) Get(ctx *runtime.Context, id string) (types.Asset, bool) {
	raw, ok := ctx.Store.Get(assetKey(id))
	if !ok {
		return types.Asset{}, false
	}
	var a types.Asset
	if err := runtime.FromJSON(raw, &a); err != nil {
		return types.Asset{}, false
	}
	return a, true
}

func (k Keeper) Freeze(ctx *runtime.Context, actor, id string) error {
	if err := k.Perms.Require(ctx, actor, permtypes.RoleGuardian); err != nil {
		return err
	}
	a, ok := k.Get(ctx, id)
	if !ok {
		return fmt.Errorf("unknown asset")
	}
	a.Status = types.StatusFrozen
	ctx.Store.Set(assetKey(id), runtime.MustJSON(a))
	ctx.Emit("asset.frozen", map[string]string{"id": id})
	return nil
}
