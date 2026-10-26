package runtime

import "github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/pkg/types"

type Event struct {
	Type       string
	Attributes map[string]string
}

type Context struct {
	Height  int64
	ChainID string
	Store   *KV
	Events  []Event
	Paused  map[string]bool
}

func NewContext(store *KV, height int64) *Context {
	return &Context{
		Height:  height,
		ChainID: types.ChainID,
		Store:   store,
		Events:  nil,
		Paused:  map[string]bool{},
	}
}

func (c *Context) Emit(typ string, attrs map[string]string) {
	c.Events = append(c.Events, Event{Type: typ, Attributes: attrs})
}

func (c *Context) IsPaused(module string) bool {
	return c.Paused[module]
}
