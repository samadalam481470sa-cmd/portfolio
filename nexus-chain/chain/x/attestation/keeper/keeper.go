package keeper

import (
	"encoding/hex"
	"fmt"

	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/pkg/crypto"
	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/runtime"
	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/attestation/types"
	permkeeper "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/permissions/keeper"
	permtypes "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/permissions/types"
)

type Keeper struct {
	Perms permkeeper.Keeper
}

func New(perms permkeeper.Keeper) Keeper { return Keeper{Perms: perms} }

func key(id string) string { return "attestation/id/" + id }

func signBytes(a types.Attestation) []byte {
	return []byte(a.ID + "|" + a.SubjectRef + "|" + a.SchemaID + "|" + a.PayloadHash)
}

func (k Keeper) Anchor(ctx *runtime.Context, a types.Attestation) error {
	if ctx.IsPaused(types.ModuleName) {
		return fmt.Errorf("attestation paused")
	}
	if err := k.Perms.Require(ctx, a.Signer, permtypes.RoleAttestor); err != nil {
		return err
	}
	if a.ID == "" || a.PayloadHash == "" {
		return fmt.Errorf("id and payload_hash required")
	}
	if _, ok := ctx.Store.Get(key(a.ID)); ok {
		return fmt.Errorf("attestation exists")
	}
	pub, err := crypto.ParsePub(a.PubKeyHex)
	if err != nil {
		return err
	}
	sig, err := hex.DecodeString(a.SignatureHex)
	if err != nil {
		return err
	}
	if !crypto.Verify(pub, signBytes(a), sig) {
		return fmt.Errorf("bad attestation signature")
	}
	a.Status = types.StatusAnchored
	a.AnchoredHeight = ctx.Height
	ctx.Store.Set(key(a.ID), runtime.MustJSON(a))
	ctx.Emit("attestation.anchored", map[string]string{"id": a.ID, "hash": a.PayloadHash})
	return nil
}

func (k Keeper) Get(ctx *runtime.Context, id string) (types.Attestation, bool) {
	raw, ok := ctx.Store.Get(key(id))
	if !ok {
		return types.Attestation{}, false
	}
	var a types.Attestation
	if err := runtime.FromJSON(raw, &a); err != nil {
		return types.Attestation{}, false
	}
	return a, true
}
