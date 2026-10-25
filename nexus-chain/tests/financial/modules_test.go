package financial_test

import (
	"encoding/hex"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/app"
	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/pkg/crypto"
	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/pkg/types"
	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/runtime"
	assettypes "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/assetregistry/types"
	atttypes "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/attestation/types"
	oracletypes "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/oracle/types"
	settletypes "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/settlement/types"
)

func TestHappyPathSettlement(t *testing.T) {
	a := app.New()
	kp, err := crypto.Generate()
	require.NoError(t, err)
	admin := kp.Address()
	require.NoError(t, a.BootstrapGenesis(admin))

	require.NoError(t, a.Deliver(func(ctx *runtime.Context) error {
		require.NoError(t, a.Assets.Register(ctx, admin, assettypes.Asset{
			ID: "a1", Denom: "ucash", DisplayName: "Cash", Decimals: 6, AssetClass: "FIAT_SYNTH",
		}))
		require.NoError(t, a.Settle.Mint(ctx, admin, admin, types.NativeDenom, 5_000_000))
		require.NoError(t, a.Oracle.Submit(ctx, admin, oracletypes.Report{
			ID: "r1", FeedID: "NXN-USD", Value: "1", Decimals: 0,
			TimestampUnix: 1, ExpiresHeight: ctx.Height + 50,
		}))
		ph := types.HashHex([]byte("demo"))
		msg := []byte("att1|sub|sch|" + ph)
		sig := crypto.Sign(kp.Private, msg)
		return a.Attest.Anchor(ctx, atttypes.Attestation{
			ID: "att1", SubjectRef: "sub", SchemaID: "sch", PayloadHash: ph,
			Signer: admin, SignatureHex: hex.EncodeToString(sig),
			PubKeyHex: hex.EncodeToString(kp.Public), ObservedAtUnix: 1,
		})
	}))

	recv := "nexusreceiver"
	require.NoError(t, a.Deliver(func(ctx *runtime.Context) error {
		return a.Settle.Settle(ctx, admin, settletypes.Intent{
			ID: "s1",
			Legs: []settletypes.Leg{{
				From: admin, To: recv, Denom: types.NativeDenom, Amount: 1_000_000,
			}},
			OracleFeed: "NXN-USD", AttestationRef: "att1",
			ResourceLocks: []string{admin, recv},
		})
	}))
	require.Equal(t, int64(1_000_000), a.Settle.GetBalance(a.Context(), recv, types.NativeDenom))
	require.Equal(t, int64(4_000_000), a.Settle.GetBalance(a.Context(), admin, types.NativeDenom))
}

func TestBadAttestationRejected(t *testing.T) {
	a := app.New()
	kp, _ := crypto.Generate()
	admin := kp.Address()
	require.NoError(t, a.BootstrapGenesis(admin))
	err := a.Deliver(func(ctx *runtime.Context) error {
		return a.Attest.Anchor(ctx, atttypes.Attestation{
			ID: "x", SubjectRef: "s", SchemaID: "sch", PayloadHash: "abcd",
			Signer: admin, SignatureHex: hex.EncodeToString(make([]byte, 64)),
			PubKeyHex: hex.EncodeToString(kp.Public),
		})
	})
	require.Error(t, err)
}

func TestStaleOracleBlocksSettlement(t *testing.T) {
	a := app.New()
	kp, _ := crypto.Generate()
	admin := kp.Address()
	require.NoError(t, a.BootstrapGenesis(admin))
	require.NoError(t, a.Deliver(func(ctx *runtime.Context) error {
		require.NoError(t, a.Settle.Mint(ctx, admin, admin, types.NativeDenom, 10))
		return a.Oracle.Submit(ctx, admin, oracletypes.Report{
			ID: "r", FeedID: "F", Value: "1", Decimals: 0,
			TimestampUnix: 1, ExpiresHeight: ctx.Height + 1, // valid this block only
		})
	}))
	// advance one empty-successful block so height > expires
	require.NoError(t, a.Deliver(func(ctx *runtime.Context) error { return nil }))
	err := a.Deliver(func(ctx *runtime.Context) error {
		return a.Settle.Settle(ctx, admin, settletypes.Intent{
			ID: "s", Legs: []settletypes.Leg{{From: admin, To: "b", Denom: types.NativeDenom, Amount: 1}},
			OracleFeed: "F",
		})
	})
	require.Error(t, err)
}

func TestProtocolGuardPause(t *testing.T) {
	a := app.New()
	kp, _ := crypto.Generate()
	admin := kp.Address()
	require.NoError(t, a.BootstrapGenesis(admin))
	require.NoError(t, a.Deliver(func(ctx *runtime.Context) error {
		return a.Guard.SetPaused(ctx, admin, "settlement", true)
	}))
	require.NoError(t, a.Deliver(func(ctx *runtime.Context) error {
		return a.Settle.Mint(ctx, admin, admin, types.NativeDenom, 100)
	}))
	err := a.Deliver(func(ctx *runtime.Context) error {
		return a.Settle.Settle(ctx, admin, settletypes.Intent{
			ID: "s", Legs: []settletypes.Leg{{From: admin, To: "b", Denom: types.NativeDenom, Amount: 1}},
		})
	})
	require.Error(t, err)
}
