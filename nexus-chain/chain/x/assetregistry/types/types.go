package types

const ModuleName = "assetregistry"

type AssetStatus string

const (
	StatusActive  AssetStatus = "ACTIVE"
	StatusFrozen  AssetStatus = "FROZEN"
	StatusRetired AssetStatus = "RETIRED"
)

type Asset struct {
	ID           string      `json:"id"`
	Denom        string      `json:"denom"`
	DisplayName  string      `json:"display_name"`
	Decimals     uint32      `json:"decimals"`
	Issuer       string      `json:"issuer"`
	AssetClass   string      `json:"asset_class"`
	Status       AssetStatus `json:"status"`
	CreatedHeight int64      `json:"created_height"`
	MetadataURI  string      `json:"metadata_uri"`
}
