package banking

import "context"

type Snapshot struct {
	AccountRef  string
	Currency    string
	Amount      string
	PayloadHash string
	Signature   string
}

type Connector interface {
	FetchBalanceSnapshot(ctx context.Context, accountRef string) (Snapshot, error)
}

type Stub struct{}

func (Stub) FetchBalanceSnapshot(ctx context.Context, accountRef string) (Snapshot, error) {
	return Snapshot{}, ErrNotAuthorized
}

var ErrNotAuthorized = errNA{}

type errNA struct{}

func (errNA) Error() string {
	return "banking connector not authorized in this environment (scaffold stub)"
}
