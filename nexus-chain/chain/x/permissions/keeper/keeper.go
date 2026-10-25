package keeper

import (
	"fmt"
	"sort"

	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/runtime"
	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/permissions/types"
)

type Keeper struct{}

func New() Keeper { return Keeper{} }

func key(addr string) string { return "permissions/bind/" + addr }

func (k Keeper) Get(ctx *runtime.Context, addr string) (types.Binding, bool) {
	raw, ok := ctx.Store.Get(key(addr))
	if !ok {
		return types.Binding{}, false
	}
	var b types.Binding
	if err := runtime.FromJSON(raw, &b); err != nil {
		return types.Binding{}, false
	}
	return b, true
}

func (k Keeper) Set(ctx *runtime.Context, b types.Binding) error {
	if b.Address == "" {
		return fmt.Errorf("empty address")
	}
	roles := uniqueSorted(b.Roles)
	b.Roles = roles
	ctx.Store.Set(key(b.Address), runtime.MustJSON(b))
	ctx.Emit("permissions.set", map[string]string{"address": b.Address})
	return nil
}

func (k Keeper) HasRole(ctx *runtime.Context, addr, role string) bool {
	b, ok := k.Get(ctx, addr)
	if !ok {
		return false
	}
	for _, r := range b.Roles {
		if r == role {
			return true
		}
	}
	return false
}

func (k Keeper) Require(ctx *runtime.Context, addr, role string) error {
	if !k.HasRole(ctx, addr, role) {
		return fmt.Errorf("address %s missing role %s", addr, role)
	}
	return nil
}

func uniqueSorted(in []string) []string {
	m := map[string]struct{}{}
	for _, r := range in {
		m[r] = struct{}{}
	}
	out := make([]string, 0, len(m))
	for r := range m {
		out = append(out, r)
	}
	sort.Strings(out)
	return out
}
