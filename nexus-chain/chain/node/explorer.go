package node

import (
	"fmt"
	"html/template"
	"strings"

	"github.com/samadalam481470sa-cmd/portfolio/nexus-chain/chain/pkg/types"
)

func renderExplorer(chainID string, height int64, appHash string, supply int64, treasury string) string {
	nxn := float64(supply) / float64(types.NXNFactor)
	tpl := `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>NEXUS — Live NXN Ledger</title>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<style>
:root { --bg:#071018; --card:#0d1b24; --fg:#e8f4f0; --accent:#2fd3a2; --muted:#7f9a92; }
*{box-sizing:border-box}
body{margin:0;font-family:"IBM Plex Sans",system-ui,sans-serif;background:
 radial-gradient(900px 500px at 80% -10%,#12352c,transparent),
 linear-gradient(165deg,#071018,#0a161c 55%,#061016);color:var(--fg);min-height:100vh}
header{padding:2rem 1.5rem 1rem;max-width:960px;margin:0 auto}
h1{font-family:"IBM Plex Serif",Georgia,serif;font-size:2.4rem;margin:0;letter-spacing:-.02em}
.sub{color:var(--muted);margin-top:.4rem}
main{max-width:960px;margin:0 auto;padding:0 1.5rem 3rem;display:grid;gap:1rem}
.card{background:var(--card);border:1px solid #1c3340;border-radius:14px;padding:1.1rem 1.2rem}
.k{color:var(--muted);font-size:.85rem} .v{font-size:1.15rem;word-break:break-all}
code{background:#112029;padding:.15rem .35rem;border-radius:6px}
a{color:var(--accent)}
.row{display:grid;grid-template-columns:1fr 1fr;gap:1rem}
@media(max-width:700px){.row{grid-template-columns:1fr}}
input,button{font:inherit;padding:.55rem .7rem;border-radius:8px;border:1px solid #2a4552;background:#0b1820;color:var(--fg)}
button{background:var(--accent);color:#042017;border:none;font-weight:600;cursor:pointer}
#out{white-space:pre-wrap;font-size:.9rem}
</style>
</head>
<body>
<header>
  <h1>NEXUS</h1>
  <p class="sub">Live public-testnet crypto ledger — native asset <strong>NXN</strong> ({{.Denom}})</p>
</header>
<main>
  <div class="row">
    <div class="card"><div class="k">Chain</div><div class="v"><code>{{.ChainID}}</code></div></div>
    <div class="card"><div class="k">Height</div><div class="v" id="h">{{.Height}}</div></div>
  </div>
  <div class="card"><div class="k">App hash</div><div class="v"><code id="hash">{{.AppHash}}</code></div></div>
  <div class="row">
    <div class="card"><div class="k">Total supply</div><div class="v">{{.SupplyNXN}} NXN</div></div>
    <div class="card"><div class="k">Treasury</div><div class="v"><code>{{.Treasury}}</code></div></div>
  </div>
  <div class="card">
    <div class="k">Create wallet / faucet / balance</div>
    <p style="margin:.6rem 0">
      <button type="button" onclick="createWallet()">Create wallet</button>
      <button type="button" onclick="faucet()">Claim faucet (10 NXN)</button>
    </p>
    <p><input id="addr" placeholder="nexus…" style="width:100%"/></p>
    <p><button type="button" onclick="bal()">Check balance</button></p>
    <pre id="out"></pre>
  </div>
  <div class="card">
    <div class="k">API</div>
    <p><a href="/v1/status">/v1/status</a> · <a href="/v1/supply">/v1/supply</a> · <a href="/v1/blocks/latest">/v1/blocks/latest</a> · <a href="/docs">OpenAPI notes in README</a></p>
    <p class="k">Educational / portfolio public testnet. Not a listed exchange asset. Not a stock. Software MIT/Apache; value and listings are not guaranteed.</p>
  </div>
</main>
<script>
async function createWallet(){
  const r=await fetch('/v1/wallet/create',{method:'POST'});
  const j=await r.json();
  document.getElementById('addr').value=j.address;
  document.getElementById('out').textContent=JSON.stringify(j,null,2);
  localStorage.setItem('nexus_wallet',JSON.stringify(j));
}
async function faucet(){
  const address=document.getElementById('addr').value.trim();
  const r=await fetch('/v1/faucet',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({address})});
  document.getElementById('out').textContent=await r.text();
}
async function bal(){
  const address=document.getElementById('addr').value.trim();
  const r=await fetch('/v1/balance?address='+encodeURIComponent(address));
  document.getElementById('out').textContent=await r.text();
}
setInterval(async()=>{
  const r=await fetch('/v1/status'); const j=await r.json();
  document.getElementById('h').textContent=j.height;
  document.getElementById('hash').textContent=j.app_hash;
},2000);
</script>
</body></html>`
	type data struct {
		ChainID, AppHash, Treasury, Denom string
		Height                            int64
		SupplyNXN                         string
	}
	d := data{
		ChainID: chainID, Height: height, AppHash: appHash, Treasury: treasury,
		Denom: types.NativeDenom, SupplyNXN: fmt.Sprintf("%.0f", nxn),
	}
	var b strings.Builder
	t := template.Must(template.New("x").Parse(tpl))
	_ = t.Execute(&b, d)
	return b.String()
}
