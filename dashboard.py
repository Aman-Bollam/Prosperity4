#!/usr/bin/env python3
"""
dashboard.py — Generates a static HTML dashboard for Prosperity logs.

No server. Opens instantly in your browser.
All interactivity (product switching, normalization, trade filters) runs
client-side via Plotly.js — zero latency on every control change.

Usage:
    python dashboard.py                    # latest log in backtests/
    python dashboard.py backtests/foo.log
    python dashboard.py backtests/foo.log --no-open   # just write HTML
"""

import csv, glob, json, os, sys, webbrowser
from pathlib import Path

import numpy as np
import pandas as pd

# ═══════════════════════════════════════════════════════════════════════════════
# PARSING
# ═══════════════════════════════════════════════════════════════════════════════

def parse_log(filepath: str):
    with open(filepath) as f:
        data = json.load(f)

    # ── Orderbook ────────────────────────────────────────────────────────────
    ob_rows = []
    for line in data["activitiesLog"].strip().splitlines()[1:]:  # skip header
        parts = line.split(";")
        if len(parts) < 17:
            continue
        try:
            def fv(s): return float(s) if s.strip() else None
            ob_rows.append({
                "day":   int(parts[0]),   "ts":  int(parts[1]),  "product": parts[2].strip(),
                "b1p":   fv(parts[3]),    "b1v": fv(parts[4]),
                "b2p":   fv(parts[5]),    "b2v": fv(parts[6]),
                "b3p":   fv(parts[7]),    "b3v": fv(parts[8]),
                "a1p":   fv(parts[9]),    "a1v": fv(parts[10]),
                "a2p":   fv(parts[11]),   "a2v": fv(parts[12]),
                "a3p":   fv(parts[13]),   "a3v": fv(parts[14]),
                "mid":   fv(parts[15]),   "pnl": fv(parts[16]),
            })
        except Exception:
            pass

    ob_df = pd.DataFrame(ob_rows)

    # ── Trades ───────────────────────────────────────────────────────────────
    trade_rows = []
    for t in data.get("tradeHistory", []):
        buyer  = t.get("buyer", "")
        seller = t.get("seller", "")
        qty    = float(t.get("quantity", 0))
        if buyer == "SUBMISSION" or seller == "SUBMISSION":
            ttype = "F"
        elif buyer == "" or seller == "":
            ttype = "M"
        elif qty >= 10:
            ttype = "B"
        else:
            ttype = "S"
        trade_rows.append({
            "ts": int(t.get("timestamp", 0)), "product": t.get("symbol", ""),
            "price": float(t.get("price", 0)), "qty": qty,
            "buyer": buyer, "seller": seller, "type": ttype,
        })
    trades_df = pd.DataFrame(trade_rows) if trade_rows else pd.DataFrame()

    # ── Sandbox logs ─────────────────────────────────────────────────────────
    pos_rows   = []
    logs_map   = {}
    orders_map = {}
    for entry in data.get("logs", []):
        ts = int(entry.get("timestamp", 0))
        ll = entry.get("lambdaLog", "")
        if not ll:
            continue
        try:
            p = json.loads(ll)
            pos     = p[0][6] if len(p[0]) > 6 else {}
            orders  = p[1] if len(p) > 1 else []
            log_str = p[4] if len(p) > 4 else ""
            for product, pv in pos.items():
                pos_rows.append({"ts": ts, "product": product, "pos": float(pv)})
            if log_str:
                logs_map[ts] = log_str
            if orders:
                orders_map[ts] = [[o[0], int(o[1]), int(o[2])] for o in orders]
        except Exception:
            pass

    pos_df = pd.DataFrame(pos_rows) if pos_rows else pd.DataFrame()
    return ob_df, trades_df, pos_df, logs_map, orders_map


# ═══════════════════════════════════════════════════════════════════════════════
# DATA PREPARATION FOR JS
# ═══════════════════════════════════════════════════════════════════════════════

def wall_mid_vec(ob: pd.DataFrame, thresh=8) -> np.ndarray:
    n  = len(ob)
    bw = np.full(n, np.nan)
    aw = np.full(n, np.nan)
    for lvl, bp, bv, ap, av in [
        (1, "b1p","b1v","a1p","a1v"),
        (2, "b2p","b2v","a2p","a2v"),
        (3, "b3p","b3v","a3p","a3v"),
    ]:
        for arr, pc, vc in [(bw, bp, bv), (aw, ap, av)]:
            p = pd.to_numeric(ob.get(pc, pd.Series(dtype=float)), errors="coerce").values
            v = pd.to_numeric(ob.get(vc, pd.Series(dtype=float)), errors="coerce").values
            m = np.isnan(arr) & ~np.isnan(p) & ~np.isnan(v) & (v >= thresh)
            arr[m] = p[m]
    both = ~np.isnan(bw) & ~np.isnan(aw)
    r = np.full(n, np.nan)
    r[both] = (bw[both] + aw[both]) / 2
    return r


def prepare_js_data(ob_df, trades_df, pos_df, logs_map, orders_map):
    products = sorted(ob_df["product"].dropna().unique().tolist()) if len(ob_df) else []
    js = {"products": products, "ob": {}, "trades": {}, "pos": {}}

    def clean(lst):
        return [None if (v is None or (isinstance(v, float) and v != v)) else v for v in lst]

    for p in products:
        ob = ob_df[ob_df["product"] == p].reset_index(drop=True)
        ts = ob["ts"].tolist()
        wm = clean(wall_mid_vec(ob).tolist())
        bm = clean(((pd.to_numeric(ob.get("b1p"), errors="coerce") +
                     pd.to_numeric(ob.get("a1p"), errors="coerce")) / 2).tolist())

        levels = []
        for side in ["b", "a"]:
            for i in [1, 2, 3]:
                pp = clean(pd.to_numeric(ob.get(f"{side}{i}p"), errors="coerce").tolist())
                vv = clean(pd.to_numeric(ob.get(f"{side}{i}v"), errors="coerce").tolist())
                levels.append({"p": pp, "v": vv})

        pnl = clean(pd.to_numeric(ob.get("pnl"), errors="coerce").tolist())

        js["ob"][p] = {
            "ts": ts, "wm": wm, "bm": bm,
            "levels": levels,   # [b1,b2,b3,a1,a2,a3] each {p,v}
            "pnl": pnl,
        }

        if len(trades_df):
            tr = trades_df[trades_df["product"] == p]
            js["trades"][p] = tr[["ts","price","qty","buyer","seller","type"]].to_dict("records")
        else:
            js["trades"][p] = []

        if len(pos_df):
            ps = pos_df[pos_df["product"] == p]
            js["pos"][p] = ps[["ts","pos"]].to_dict("records")
        else:
            js["pos"][p] = []

    # Convert logs/orders keys to strings for JSON
    js["logs"]   = {str(k): v for k, v in logs_map.items()}
    js["orders"] = {
        str(k): [o for o in v]
        for k, v in orders_map.items()
    }
    return js


# ═══════════════════════════════════════════════════════════════════════════════
# HTML GENERATION
# ═══════════════════════════════════════════════════════════════════════════════

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Prosperity Dashboard</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: #0d0d0d; color: #e0e0e0;
  font-family: ui-monospace,'JetBrains Mono','Fira Code',monospace;
  font-size: 13px; height: 100vh; display: flex; flex-direction: column;
}
#titlebar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 6px 18px; background: #111; border-bottom: 1px solid #1e1e1e;
  flex-shrink: 0;
}
#titlebar .title { color: #444; font-size: 10px; letter-spacing: 4px; }
#titlebar .legend { display: flex; gap: 8px; font-size: 11px; }
.pill {
  padding: 2px 8px; border-radius: 3px; color: #fff; font-size: 10px;
  font-weight: 600;
}
#controls {
  display: flex; flex-wrap: wrap; align-items: flex-end; gap: 22px;
  padding: 12px 18px; background: #111; border-bottom: 1px solid #1e1e1e;
  flex-shrink: 0;
}
#filters {
  display: flex; flex-wrap: wrap; align-items: flex-end; gap: 24px;
  padding: 10px 18px; background: #111; border-bottom: 1px solid #1e1e1e;
  flex-shrink: 0;
}
#statsbar {
  display: flex; gap: 10px; padding: 8px 18px;
  background: #0f0f0f; border-bottom: 1px solid #1e1e1e;
  flex-shrink: 0;
}
.stat-card {
  background: #161616; border: 1px solid #252525; border-radius: 5px;
  padding: 7px 18px; min-width: 95px; text-align: center;
}
.stat-label { font-size: 9px; color: #555; letter-spacing: 1.5px; margin-bottom: 3px; }
.stat-value { font-size: 20px; font-weight: 700; color: #e8e8e8; }
#body { display: flex; flex: 1; overflow: hidden; }
#chart-div { flex: 1; min-width: 0; }
#log-panel {
  width: 270px; flex-shrink: 0; background: #0a0a0a;
  border-left: 1px solid #1e1e1e; display: flex; flex-direction: column;
}
#log-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 14px; background: #111; border-bottom: 1px solid #1e1e1e;
  flex-shrink: 0;
}
#log-header span { font-size: 10px; letter-spacing: 2px; color: #666; }
#log-ts { color: #444; font-size: 11px; }
#log-content {
  flex: 1; overflow-y: auto; padding: 12px 14px;
  color: #888; font-size: 11.5px; white-space: pre-wrap;
  word-break: break-word; line-height: 1.6;
}
/* Controls */
.ctrl-group { display: flex; flex-direction: column; }
.ctrl-label {
  font-size: 9px; color: #666; letter-spacing: 1.5px;
  margin-bottom: 6px; font-weight: 600;
}
select, .btn-group button {
  background: #1a1a1a; border: 1px solid #333; color: #ddd;
  padding: 6px 10px; border-radius: 4px; font-size: 12px;
  font-family: inherit; cursor: pointer; outline: none;
}
select:hover, .btn-group button:hover { border-color: #555; }
select:focus { border-color: #666; }
.btn-group { display: flex; gap: 4px; flex-wrap: wrap; }
.btn-group button {
  padding: 5px 11px; font-size: 11px; transition: background 0.1s;
}
.btn-group button.active {
  background: #2a2a3a; border-color: #5b5bd6; color: #aab;
}
.checkgroup { display: flex; gap: 8px; flex-wrap: wrap; }
.checkgroup label {
  display: flex; align-items: center; gap: 5px;
  cursor: pointer; color: #bbb; font-size: 12px; padding: 4px 8px;
  border: 1px solid #2a2a2a; border-radius: 4px;
  transition: border-color 0.1s;
}
.checkgroup label:hover { border-color: #444; }
.checkgroup input[type=checkbox] { accent-color: #5b5bd6; }
/* Range slider */
input[type=range] {
  -webkit-appearance: none; appearance: none;
  background: #2a2a2a; height: 3px; border-radius: 2px; outline: none;
  width: 200px; cursor: pointer;
}
input[type=range]::-webkit-slider-thumb {
  -webkit-appearance: none; appearance: none;
  width: 14px; height: 14px; border-radius: 50%;
  background: #5b5bd6; cursor: pointer;
}
.range-row { display: flex; align-items: center; gap: 8px; }
.range-val { color: #888; font-size: 11px; min-width: 24px; }
/* Scrollbar */
::-webkit-scrollbar { width: 5px; }
::-webkit-scrollbar-track { background: #111; }
::-webkit-scrollbar-thumb { background: #333; border-radius: 3px; }
</style>
</head>
<body>

<div id="titlebar">
  <span class="title">PROSPERITY  DASHBOARD</span>
  <div class="legend">
    <span class="pill" style="background:#c0392b">ASK</span>
    <span class="pill" style="background:#2471a3">BID</span>
    <span class="pill" style="background:#00bcd4">□ Maker</span>
    <span class="pill" style="background:#ff9800">△ Taker</span>
    <span class="pill" style="background:#f1c40f">✕ Own</span>
    <span class="pill" style="background:#4a4">→ Our quotes</span>
  </div>
</div>

<div id="controls">
  <div class="ctrl-group">
    <div class="ctrl-label">PRODUCT</div>
    <select id="sel-product" onchange="onProductChange()"></select>
  </div>
  <div class="ctrl-group">
    <div class="ctrl-label">NORMALIZE</div>
    <div class="btn-group">
      <button id="norm-none"    class="active" onclick="setNorm('none')">None</button>
      <button id="norm-wallmid"               onclick="setNorm('wallmid')">WallMid</button>
      <button id="norm-bestmid"               onclick="setNorm('bestmid')">Best Mid</button>
    </div>
  </div>
  <div class="ctrl-group">
    <div class="ctrl-label">OB LEVELS</div>
    <div class="checkgroup">
      <label><input type="checkbox" id="ob-l1" checked onchange="redraw()"> L1</label>
      <label><input type="checkbox" id="ob-l2" checked onchange="redraw()"> L2</label>
      <label><input type="checkbox" id="ob-l3" checked onchange="redraw()"> L3</label>
    </div>
  </div>
  <div class="ctrl-group">
    <div class="ctrl-label">LOG FILE</div>
    <select id="sel-file" onchange="onFileChange()">LOG_FILE_OPTIONS</select>
  </div>
</div>

<div id="filters">
  <div class="ctrl-group">
    <div class="ctrl-label">TRADER TYPE</div>
    <div class="checkgroup">
      <label><input type="checkbox" id="type-M" checked onchange="redraw()"> Maker (M)</label>
      <label><input type="checkbox" id="type-S" checked onchange="redraw()"> Small (S)</label>
      <label><input type="checkbox" id="type-B" checked onchange="redraw()"> Big (B)</label>
      <label><input type="checkbox" id="type-I" checked onchange="redraw()"> Informed (I)</label>
      <label><input type="checkbox" id="type-F" checked onchange="redraw()"> Own (F)</label>
    </div>
  </div>
  <div class="ctrl-group">
    <div class="ctrl-label">QUANTITY RANGE</div>
    <div class="range-row">
      <span class="range-val" id="qty-lo-val">1</span>
      <input type="range" id="qty-lo" min="1" max="50" value="1"
             oninput="document.getElementById('qty-lo-val').textContent=this.value; redraw()">
      <span style="color:#444">–</span>
      <input type="range" id="qty-hi" min="1" max="50" value="50"
             oninput="document.getElementById('qty-hi-val').textContent=this.value; redraw()">
      <span class="range-val" id="qty-hi-val">50</span>
    </div>
  </div>
</div>

<div id="statsbar">
  <div class="stat-card"><div class="stat-label">TIMESTAMP</div><div class="stat-value" id="s-ts">—</div></div>
  <div class="stat-card"><div class="stat-label">MID PRICE</div><div class="stat-value" id="s-mid">—</div></div>
  <div class="stat-card"><div class="stat-label">PnL</div><div class="stat-value" id="s-pnl">—</div></div>
  <div class="stat-card"><div class="stat-label">POSITION</div><div class="stat-value" id="s-pos">—</div></div>
  <div class="stat-card"><div class="stat-label">SPREAD</div><div class="stat-value" id="s-spread">—</div></div>
</div>

<div id="body">
  <div id="chart-div"></div>
  <div id="log-panel">
    <div id="log-header">
      <span>LOG VIEWER</span>
      <span id="log-ts">hover to sync</span>
    </div>
    <div id="log-content">(hover on chart to see log output)</div>
  </div>
</div>

<script>
const DATA = __DATA__;

// ── Fixed trace indices (never change after initChart) ────────────────────────
// 0-2: Bid L1-L3  |  3-5: Ask L1-L3  |  6: WallMid
// 7: Our Bid  |  8: Our Ask
// 9-13: Trades F,M,S,B,I  |  14: PnL  |  15: Position
const TI = { B:[0,1,2], A:[3,4,5], WM:6, QB:7, QA:8,
             TR:{F:9,M:10,S:11,B:12,I:13}, PNL:14, POS:15 };
const TTYPES = ['F','M','S','B','I'];
const TSTYLE = {
  F:{symbol:'cross',       color:'#FFD700', name:'Own (F)'},
  M:{symbol:'square',      color:'#00bcd4', name:'Maker (M)'},
  S:{symbol:'triangle-up', color:'#FF9800', name:'Small (S)'},
  B:{symbol:'triangle-up', color:'#FF5722', name:'Big (B)'},
  I:{symbol:'diamond',     color:'#E040FB', name:'Informed (I)'},
};
const BCOLS = ['rgba(50,110,210,0.85)','rgba(70,90,190,0.5)','rgba(70,90,170,0.3)'];
const ACOLS = ['rgba(210,50,50,0.85)', 'rgba(190,70,70,0.5)', 'rgba(170,70,70,0.3)'];

// ── State ─────────────────────────────────────────────────────────────────────
let product = DATA.products[0] || '';
let norm    = 'none';
let lastTs  = null;
const _off  = {};   // product -> {none, wallmid, bestmid}  (Float64Array)
const _tsMap = {};  // product -> Map<ts, index>

// ── Init product selector ─────────────────────────────────────────────────────
(function() {
  const sel = document.getElementById('sel-product');
  DATA.products.forEach(p => { const o=document.createElement('option'); o.value=o.textContent=p; sel.appendChild(o); });
})();

// ── Offset cache ──────────────────────────────────────────────────────────────
function cacheOffsets(p) {
  if (_off[p]) return;
  const ob = DATA.ob[p], n = ob.ts.length;
  const wm = new Float64Array(ob.wm.map((w,i) => w ?? ob.bm[i] ?? 0));
  _off[p] = { none: new Float64Array(n), wallmid: wm, bestmid: new Float64Array(ob.bm.map(v=>v??0)) };
  const m = new Map(); ob.ts.forEach((t,i) => m.set(t,i)); _tsMap[p] = m;
}

function offset(p, n) { cacheOffsets(p); return _off[p][n]; }

function subArr(arr, off) { return arr.map((v,i) => v===null ? null : v - off[i]); }

// ── Trace builders ────────────────────────────────────────────────────────────
function obTrace(side, li, ob, off, vis) {
  const lv = ob.levels[side==='b' ? li : li+3];
  return { x:ob.ts, y:subArr(lv.p, off), mode:'markers', type:'scattergl',
    name:`${side==='b'?'Bid':'Ask'} L${li+1}`, legendgroup:side, showlegend:li===0,
    visible:vis,
    marker:{color:(side==='b'?BCOLS:ACOLS)[li], size:lv.v.map(v=>v?Math.min(Math.max(v*1.8,3),18):3)},
    hovertemplate:`${side==='b'?'Bid':'Ask'} L${li+1}: %{y:.1f}<extra></extra>` };
}

function wmTrace(ob, off, vis) {
  return { x:ob.ts, y:ob.wm.map((w,i)=>w===null?null:w-off[i]), mode:'lines', type:'scattergl',
    name:'WallMid', visible:vis, line:{color:'rgba(255,255,255,0.3)',width:1,dash:'dot'},
    hovertemplate:'WallMid: %{y:.2f}<extra></extra>' };
}

function quoteTraces(ob, off) {
  const bx=[],by=[],ax=[],ay=[];
  ob.ts.forEach((t,i)=>{
    (DATA.orders[String(t)]||[]).forEach(([sym,pr,qty])=>{
      if(sym!==product) return;
      if(qty>0){bx.push(t);by.push(pr-off[i]);}else{ax.push(t);ay.push(pr-off[i]);}
    });
  });
  const mk=(x,y,nm,c)=>({x,y,mode:'markers',type:'scatter',name:nm,visible:x.length>0,
    marker:{symbol:'line-ew',color:c,size:12,line:{width:2,color:c}},
    hovertemplate:`${nm}: %{y:.0f}<extra></extra>`});
  return [mk(bx,by,'Our Bid','rgba(80,200,120,0.6)'), mk(ax,ay,'Our Ask','rgba(200,100,60,0.6)')];
}

function tradeTrace(tt, off, qlo, qhi, vis) {
  const s = TSTYLE[tt];
  const tr = (DATA.trades[product]||[]).filter(t=>t.type===tt&&t.qty>=qlo&&t.qty<=qhi);
  if (!tr.length) return {x:[],y:[],mode:'markers',type:'scatter',name:s.name,
    visible:false, marker:{symbol:s.symbol,color:s.color,size:[]}, customdata:[],
    hovertemplate:'%{customdata}<extra></extra>'};
  const m=_tsMap[product], o=_off[product][norm];
  return { x:tr.map(t=>t.ts),
    y:tr.map(t=>{ const i=m?.get(t.ts)??-1; return t.price-(i>=0?o[i]:0); }),
    mode:'markers', type:'scatter', name:s.name, visible:vis,
    marker:{symbol:s.symbol,color:s.color,size:tr.map(t=>Math.min(Math.max(t.qty*2.5,6),22)),
            line:{width:1,color:'rgba(255,255,255,0.4)'}},
    customdata:tr.map(t=>`${s.name}\nBuyer: ${t.buyer||'—'}  Seller: ${t.seller||'—'}\nQty: ${t.qty}  Price: ${t.price}`),
    hovertemplate:'%{customdata}<extra></extra>' };
}

function buildAllTraces(p, n) {
  cacheOffsets(p);
  const ob=DATA.ob[p], pos=DATA.pos[p]||[], off=_off[p][n];
  const L=[chk('ob-l1'),chk('ob-l2'),chk('ob-l3')];
  const qlo=+v('qty-lo'), qhi=+v('qty-hi');
  const traces=new Array(16);
  for(let i=0;i<3;i++){traces[TI.B[i]]=obTrace('b',i,ob,off,L[i]); traces[TI.A[i]]=obTrace('a',i,ob,off,L[i]);}
  traces[TI.WM]=wmTrace(ob,off,n!=='wallmid');
  const [qb,qa]=quoteTraces(ob,off); traces[TI.QB]=qb; traces[TI.QA]=qa;
  TTYPES.forEach((tt,i)=>traces[TI.TR[tt]]=tradeTrace(tt,off,qlo,qhi,chk('type-'+tt)));
  traces[TI.PNL]={x:ob.ts,y:ob.pnl,mode:'lines',type:'scatter',name:'PnL',fill:'tozeroy',
    line:{color:'#00E676',width:1.5},fillcolor:'rgba(0,230,118,0.07)',xaxis:'x',yaxis:'y2',
    hovertemplate:'PnL: %{y:.0f}<extra></extra>'};
  traces[TI.POS]=pos.length?{x:pos.map(r=>r.ts),y:pos.map(r=>r.pos),mode:'lines',type:'scatter',
    name:'Position',fill:'tozeroy',line:{color:'#40C4FF',width:1.5},fillcolor:'rgba(64,196,255,0.07)',
    xaxis:'x',yaxis:'y3',hovertemplate:'Pos: %{y}<extra></extra>'}
    :{x:[],y:[],mode:'lines',type:'scatter',name:'Position',xaxis:'x',yaxis:'y3'};
  return traces;
}

// ── Layout ────────────────────────────────────────────────────────────────────
function makeLayout() {
  const yl=norm==='wallmid'?'Δ WallMid':norm==='bestmid'?'Δ BestMid':'Price';
  return {paper_bgcolor:'#0d0d0d',plot_bgcolor:'#111',margin:{l:62,r:10,t:12,b:40},
    hovermode:'x unified',
    legend:{orientation:'h',yanchor:'bottom',y:1.01,x:0,font:{size:11},bgcolor:'rgba(0,0,0,0)'},
    xaxis:{domain:[0,1],gridcolor:'#1e1e1e',color:'#666'},
    yaxis:{domain:[0.35,1],gridcolor:'#1e1e1e',color:'#888',title:{text:yl,font:{size:11}}},
    yaxis2:{domain:[0.185,0.33],gridcolor:'#1e1e1e',color:'#888',title:{text:'PnL',font:{size:11}}},
    yaxis3:{domain:[0,0.175],gridcolor:'#1e1e1e',color:'#888',title:{text:'Pos',font:{size:11}}},
    font:{family:'ui-monospace,monospace',color:'#888'},
    shapes:[{type:'line',xref:'paper',x0:0,x1:1,yref:'y2',y0:0,y1:0,line:{color:'rgba(255,255,255,0.1)',width:1}},
            {type:'line',xref:'paper',x0:0,x1:1,yref:'y3',y0:0,y1:0,line:{color:'rgba(255,255,255,0.1)',width:1}}]};
}

// ── DOM helpers ───────────────────────────────────────────────────────────────
function chk(id){ return document.getElementById(id).checked; }
function v(id)  { return document.getElementById(id).value; }

// ── Initial render ────────────────────────────────────────────────────────────
function initChart() {
  Plotly.newPlot('chart-div', buildAllTraces(product,norm), makeLayout(),
    {scrollZoom:true,displayModeBar:false,responsive:true});
  document.getElementById('chart-div').on('plotly_hover', e => {
    if (e.points?.length) updateStats(e.points[0].x);
  });
}

// ── Fast norm update: single Plotly.update call ───────────────────────────────
function setNorm(n) {
  norm = n;
  ['none','wallmid','bestmid'].forEach(id =>
    document.getElementById('norm-'+id).classList.toggle('active', id===n));

  cacheOffsets(product);
  const ob=DATA.ob[product], off=_off[product][n];
  const qlo=+v('qty-lo'), qhi=+v('qty-hi');
  const m=_tsMap[product];

  const yArr=[], visArr=[], idxs=[];

  // OB levels (traces 0-5) + WallMid (trace 6)
  for(let i=0;i<3;i++){
    yArr.push(subArr(ob.levels[i].p,   off)); visArr.push(chk('ob-l'+(i+1))); idxs.push(TI.B[i]);
    yArr.push(subArr(ob.levels[i+3].p, off)); visArr.push(chk('ob-l'+(i+1))); idxs.push(TI.A[i]);
  }
  yArr.push(ob.wm.map((w,i)=>w===null?null:w-off[i]));
  visArr.push(n!=='wallmid'); idxs.push(TI.WM);
  // Our quotes (traces 7-8)
  const [qb,qa]=quoteTraces(ob,off);
  yArr.push(qb.y); visArr.push(true); idxs.push(TI.QB);
  yArr.push(qa.y); visArr.push(true); idxs.push(TI.QA);
  // Trade y values (traces 9-13)
  TTYPES.forEach(tt=>{
    const tr=(DATA.trades[product]||[]).filter(t=>t.type===tt&&t.qty>=qlo&&t.qty<=qhi);
    yArr.push(tr.map(t=>{ const i=m?.get(t.ts)??-1; return t.price-(i>=0?off[i]:0); }));
    visArr.push(chk('type-'+tt) && tr.length>0); idxs.push(TI.TR[tt]);
  });

  const yl = n==='wallmid'?'Δ WallMid':n==='bestmid'?'Δ BestMid':'Price';
  Plotly.update('chart-div', {y: yArr, visible: visArr}, {'yaxis.title.text': yl}, idxs);
}

// ── OB level toggle: restyle visibility only ──────────────────────────────────
function onObLevel() {
  for(let i=0;i<3;i++){
    const vis=chk('ob-l'+(i+1));
    Plotly.restyle('chart-div',{visible:vis},[TI.B[i],TI.A[i]]);
  }
}

// ── Trade type toggle: restyle visibility only ────────────────────────────────
function onTradeType(tt) {
  Plotly.restyle('chart-div',{visible:chk('type-'+tt)},[TI.TR[tt]]);
}

// ── Qty range: restyle trade data only ───────────────────────────────────────
function onQtyRange() {
  cacheOffsets(product);
  const off=_off[product][norm], qlo=+v('qty-lo'), qhi=+v('qty-hi');
  const xArr=[],yArr=[],szArr=[],cdArr=[],visArr=[];
  TTYPES.forEach(tt=>{
    const tr=(DATA.trades[product]||[]).filter(t=>t.type===tt&&t.qty>=qlo&&t.qty<=qhi);
    const m=_tsMap[product];
    xArr.push(tr.map(t=>t.ts));
    yArr.push(tr.map(t=>{ const i=m?.get(t.ts)??-1; return t.price-(i>=0?off[i]:0); }));
    szArr.push(tr.map(t=>Math.min(Math.max(t.qty*2.5,6),22)));
    cdArr.push(tr.map(t=>`${TSTYLE[tt].name}\nBuyer: ${t.buyer||'—'}  Seller: ${t.seller||'—'}\nQty: ${t.qty}  Price: ${t.price}`));
    visArr.push(chk('type-'+tt) && tr.length>0);
  });
  const idxs=TTYPES.map(tt=>TI.TR[tt]);
  Plotly.restyle('chart-div',{x:xArr,y:yArr,'marker.size':szArr,customdata:cdArr,visible:visArr},idxs);
  document.getElementById('qty-lo-val').textContent=v('qty-lo');
  document.getElementById('qty-hi-val').textContent=v('qty-hi');
}

// ── Product change: full rebuild (unavoidable) ────────────────────────────────
function onProductChange() {
  product = v('sel-product');
  Plotly.react('chart-div', buildAllTraces(product,norm), makeLayout());
}

// ── Stats + log viewer on hover ───────────────────────────────────────────────
function updateStats(ts) {
  if(lastTs===ts) return; lastTs=ts;
  const ob=DATA.ob[product];
  const idx=ob.ts.findLastIndex?ob.ts.findLastIndex(t=>t<=ts):ob.ts.reduce((a,t,i)=>t<=ts?i:a,0);
  if(idx<0) return;
  const mid=ob.bm[idx], pnl=ob.pnl[idx];
  const b1=ob.levels[0].p[idx], a1=ob.levels[3].p[idx];
  const spread=(b1!==null&&a1!==null)?a1-b1:null;
  const pos=(()=>{ const ps=DATA.pos[product]||[]; let r=0; for(const x of ps){if(x.ts<=ts)r=x.pos;else break;} return r; })();
  document.getElementById('s-ts').textContent=ts;
  document.getElementById('s-mid').textContent=mid!==null?mid.toFixed(1):'—';
  document.getElementById('s-pnl').textContent=pnl!==null?(pnl>=0?'+':'')+pnl.toFixed(0):'—';
  document.getElementById('s-pos').textContent=pos;
  document.getElementById('s-spread').textContent=spread!==null?spread.toFixed(0):'—';

  const logKeys=Object.keys(DATA.logs).map(Number);
  const lts=logKeys.length?logKeys.reduce((a,b)=>Math.abs(b-ts)<Math.abs(a-ts)?b:a):null;
  document.getElementById('log-ts').textContent=`ts ${ts}`;
  const ords=(DATA.orders[String(ts)]||[]).filter(o=>o[0]===product);
  const logStr=lts!==null?DATA.logs[String(lts)]:'';
  const lines=[];
  const bids=ords.filter(o=>o[2]>0), asks=ords.filter(o=>o[2]<0);
  if(bids.length){lines.push('OUR BIDS'); bids.forEach(o=>lines.push(`  +${o[2]} @ ${o[1]}`));}
  if(asks.length){lines.push('OUR ASKS'); asks.forEach(o=>lines.push(`  ${o[2]} @ ${o[1]}`));}
  if(logStr){if(lines.length)lines.push(''); lines.push('LOGGER OUTPUT'); lines.push(logStr);}
  if(!lines.length) lines.push('(no output)');
  document.getElementById('log-content').textContent=lines.join('\n');
}

function onFileChange(){ const f=v('sel-file'); if(f) window.location.href=f; }

// ── Wire up controls ──────────────────────────────────────────────────────────
document.getElementById('ob-l1').onchange=
document.getElementById('ob-l2').onchange=
document.getElementById('ob-l3').onchange = onObLevel;

['F','M','S','B','I'].forEach(tt=>{
  document.getElementById('type-'+tt).onchange = () => onTradeType(tt);
});

document.getElementById('qty-lo').oninput=
document.getElementById('qty-hi').oninput = onQtyRange;

// ── Boot ──────────────────────────────────────────────────────────────────────
initChart();
</script>
</body>
</html>
"""


def build_html(js_data: dict, log_files: list, current_file: str) -> str:
    # Replace NaN/None with null for JS
    data_json = json.dumps(js_data)

    # Build log file options
    file_opts = ""
    for f in log_files:
        sel = ' selected' if str(f) == str(current_file) else ''
        file_opts += f'<option value="{f}"{sel}>{Path(f).name}</option>'

    html = HTML_TEMPLATE.replace("__DATA__", data_json)
    html = html.replace("LOG_FILE_OPTIONS", file_opts)
    return html


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    no_open = "--no-open" in sys.argv
    args    = [a for a in sys.argv[1:] if not a.startswith("--")]

    if args:
        filepath = args[0]
    else:
        candidates = sorted(glob.glob("backtests/*.log"), key=os.path.getmtime, reverse=True)
        if not candidates:
            candidates = [f for f in os.listdir(".") if f.endswith(".log")]
        if not candidates:
            print("No .log file found. Run ./run.sh first.")
            sys.exit(1)
        filepath = candidates[0]
        print(f"Auto-loading: {filepath}")

    print("Parsing log...")
    ob_df, trades_df, pos_df, logs_map, orders_map = parse_log(filepath)
    print(f"  {len(ob_df):,} orderbook rows  |  {len(trades_df):,} trades  |  {len(pos_df):,} position rows")

    if len(ob_df) == 0:
        print("No data found.")
        sys.exit(1)

    products = sorted(ob_df["product"].dropna().unique().tolist())
    print(f"  Products: {products}")

    print("Building dashboard...")
    js_data   = prepare_js_data(ob_df, trades_df, pos_df, logs_map, orders_map)
    log_files = sorted(glob.glob("backtests/*.log"), key=os.path.getmtime, reverse=True)
    html      = build_html(js_data, log_files, filepath)

    out_path = Path(filepath).with_suffix(".html")
    out_path.write_text(html, encoding="utf-8")
    print(f"  Written → {out_path}  ({out_path.stat().st_size / 1e6:.1f} MB)")

    if not no_open:
        webbrowser.open(out_path.resolve().as_uri())
        print("  Opened in browser.")
