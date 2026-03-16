async function loadJson(path) {
  const r = await fetch(path);
  return await r.json();
}
function card(html) { return `<div class="card">${html}</div>`; }
async function main() {
  const status = await loadJson("./data/latest_status.json");
  const signals = await loadJson("./data/signals.json");
  const paper = await loadJson("./data/paper_trades.json");
  document.getElementById("status").innerHTML = `<div class="grid">` + status.map(s => card(`
      <strong>${s.coin}</strong><br>
      Preço: ${Number(s.price).toFixed(2)}<br>
      Tendência: ${s.trend}<br>
      Funding: ${Number(s.funding_hr_pct).toFixed(4)}%/h<br>
      RSI2: ${Number(s.rsi2).toFixed(2)}<br>
      <small>${s.time}</small>`)).join("") + `</div>`;
  document.getElementById("signals").innerHTML = signals.length ? `<div class="grid">` + signals.map(s => card(`
      <strong>${s.coin}</strong>
      <span class="badge ${s.side === "LONG" ? "long" : "short"}">${s.side}</span><br>
      Entrada: ${Number(s.entry).toFixed(2)}<br>
      Stop: ${Number(s.stop).toFixed(2)}<br>
      T1: ${Number(s.target1).toFixed(2)}<br>
      T2: ${Number(s.target2).toFixed(2)}<br>
      Funding: ${Number(s.funding_hr_pct).toFixed(4)}%/h<br>
      <small>${s.time}</small>`)).join("") + `</div>` : card("Sem sinais no momento.");
  document.getElementById("paper").innerHTML = paper.length ? `<div class="grid">` + paper.map(p => card(`
      <strong>${p.coin}</strong>
      <span class="badge ${p.side === "LONG" ? "long" : "short"}">${p.side}</span><br>
      Entrada: ${Number(p.entry).toFixed(2)}<br>
      Stop: ${Number(p.stop).toFixed(2)}<br>
      Status: ${p.status}<br>
      <small>${p.time}</small>`)).join("") + `</div>` : card("Sem paper trades.");
}
main();
