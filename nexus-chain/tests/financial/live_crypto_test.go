package financial_test

import (
	"encoding/hex"
	"path/filepath"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/node"
	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/pkg/crypto"
	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/pkg/types"
	bankkeeper "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/bank/keeper"
	btypes "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/x/bank/types"
)

func TestLiveNXNTransferAndPersist(t *testing.T) {
	home := t.TempDir()
	treasury, err := crypto.Generate()
	require.NoError(t, err)
	n, err := node.Open(node.Config{
		Home: home, Listen: ":0", BlockInterval: time.Hour, FaucetEnabled: false,
	}, treasury)
	require.NoError(t, err)

	recv, err := crypto.Generate()
	require.NoError(t, err)

	msg := btypes.MsgSend{
		From: treasury.Address(), To: recv.Address(),
		Denom: types.NativeDenom, Amount: 2_500_000, Sequence: 0, Memo: "hi",
		PubKeyHex: hex.EncodeToString(treasury.Public),
	}
	sig := crypto.Sign(treasury.Private, bankkeeper.SignBytes(msg, types.ChainID))
	msg.SigHex = hex.EncodeToString(sig)
	_, err = n.EnqueueSend(msg)
	require.NoError(t, err)
	require.NoError(t, n.ProduceBlock())

	require.Equal(t, int64(2_500_000), n.App.Balance(recv.Address(), types.NativeDenom))
	require.Greater(t, n.App.Status().Height, int64(0))

	// reopen and ensure persistence
	n2, err := node.Open(node.Config{Home: home, Listen: ":0", BlockInterval: time.Hour}, treasury)
	require.NoError(t, err)
	require.Equal(t, int64(2_500_000), n2.App.Balance(recv.Address(), types.NativeDenom))
	require.FileExists(t, filepath.Join(home, "state", "ledger.json"))
}
