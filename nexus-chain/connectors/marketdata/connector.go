package marketdata

import "context"

type Quote struct {
	Symbol    string
	Mid       string
	Timestamp int64
}

type Connector interface {
	GetMid(ctx context.Context, symbol string) (Quote, error)
}

type Stub struct{}

func (Stub) GetMid(ctx context.Context, symbol string) (Quote, error) {
	return Quote{}, ErrNotAuthorized
}

var ErrNotAuthorized = errNA{}

type errNA struct{}

func (errNA) Error() string {
	return "marketdata connector not authorized in this environment (scaffold stub)"
}
