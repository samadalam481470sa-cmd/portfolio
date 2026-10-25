package keeper

import (
	"fmt"

	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/runtime"
	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/oracle/types"
	permkeeper "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/permissions/keeper"
	permtypes "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/permissions/types"
)

type Keeper struct {
	Perms  permkeeper.Keeper
	Quorum int
}

func New(perms permkeeper.Keeper, quorum int) Keeper {
	if quorum < 1 {
		quorum = 1
	}
	return Keeper{Perms: perms, Quorum: quorum}
}

func key(id string) string         { return "oracle/report/" + id }
func latestKey(feed string) string { return "oracle/latest/" + feed }

func (k Keeper) Submit(ctx *runtime.Context, actor string, r types.Report) error {
	if ctx.IsPaused(types.ModuleName) {
		return fmt.Errorf("oracle paused")
	}
	if err := k.Perms.Require(ctx, actor, permtypes.RoleOracleReporter); err != nil {
		return err
	}
	if r.ID == "" || r.FeedID == "" {
		return fmt.Errorf("id and feed_id required")
	}
	if r.ExpiresHeight <= ctx.Height {
		return fmt.Errorf("already expired")
	}
	r.Reporters = append([]string{}, r.Reporters...)
	found := false
	for _, x := range r.Reporters {
		if x == actor {
			found = true
			break
		}
	}
	if !found {
		r.Reporters = append(r.Reporters, actor)
	}
	r.QuorumMet = len(r.Reporters) >= k.Quorum
	ctx.Store.Set(key(r.ID), runtime.MustJSON(r))
	if r.QuorumMet {
		ctx.Store.Set(latestKey(r.FeedID), []byte(r.ID))
	}
	ctx.Emit("oracle.submitted", map[string]string{"id": r.ID, "feed": r.FeedID})
	return nil
}

func (k Keeper) Latest(ctx *runtime.Context, feed string) (types.Report, error) {
	idb, ok := ctx.Store.Get(latestKey(feed))
	if !ok {
		return types.Report{}, fmt.Errorf("no feed")
	}
	raw, ok := ctx.Store.Get(key(string(idb)))
	if !ok {
		return types.Report{}, fmt.Errorf("missing report")
	}
	var r types.Report
	if err := runtime.FromJSON(raw, &r); err != nil {
		return types.Report{}, err
	}
	if !r.QuorumMet {
		return types.Report{}, fmt.Errorf("quorum not met")
	}
	if r.ExpiresHeight <= ctx.Height {
		return types.Report{}, fmt.Errorf("stale oracle report")
	}
	return r, nil
}
