/* Pure simulation model. Prices are USD/BTC, quantities BTC, P&L INR at a fixed illustrative ₹83/USD. */
(function (root) {
  const RATE = 83, PRICE = 67420, KEY = 'gj-demo-v1';
  const now = () => new Date().toISOString();
  const currentPrice = () => Math.round((PRICE + 120 * Math.sin(Math.floor(Date.now() / 5000) * 0.23)) * 100) / 100;
  const day = n => new Date(Date.now() - n * 86400000).toISOString();
  const pnl = (side, entry, exit, qty) => Math.round((side === 'Buy' ? exit - entry : entry - exit) * qty * RATE * 100) / 100;
  function seed() {
    const specs = [[18,'Buy',64200,64900],[12,'Sell',66100,65500],[7,'Buy',67000,66600],[3,'Buy',66100,66900]];
    const closed = specs.map((x,i) => ({id:'DEMO-100'+i, strategy:'GJ Crypto Time Machine', symbol:'BTCUSD', side:x[1], qty:0.01, entry:x[2], exit:x[3], pnl:pnl(x[1],x[2],x[3],0.01), status:'Closed', date:day(x[0]), closedAt:day(x[0]), stop:null, target:null}));
    return {version:1, profile:{name:'Alex Morgan',email:'student@gjacademy.com',mobile:''}, connected:true, subscriptions:[], positions:[], closed, orders:[{id:'DEMO-REJECT-01',strategy:'GJ Crypto Time Machine',symbol:'BTCUSD',side:'Buy',qty:0.01,entry:PRICE,status:'Rejected',reason:'Demo: insufficient allocated margin.',date:day(2)}], counter:1005};
  }
  function load() { try { const s=JSON.parse(localStorage.getItem(KEY)); return s && s.version===1 ? s : seed(); } catch (_) { return seed(); } }
  function save(s) { localStorage.setItem(KEY, JSON.stringify(s)); }
  function reset() { const s=seed(); save(s); return s; }
  function today(d) { return new Date(d).toDateString() === new Date().toDateString(); }
  function metrics(s, trades=s.closed) {
    const wins=trades.filter(t=>t.pnl>0), losses=trades.filter(t=>t.pnl<0), total=trades.reduce((a,t)=>a+t.pnl,0);
    let equity=0,peak=0,drawdown=0; [...trades].sort((a,b)=>new Date(a.closedAt)-new Date(b.closedAt)).forEach(t=>{equity+=t.pnl;peak=Math.max(peak,equity);drawdown=Math.max(drawdown,peak-equity)});
    const gain=wins.reduce((a,t)=>a+t.pnl,0), loss=Math.abs(losses.reduce((a,t)=>a+t.pnl,0));
    return {total, today:s.closed.filter(t=>today(t.closedAt)).reduce((a,t)=>a+t.pnl,0), monthly:s.closed.filter(t=>new Date(t.closedAt).getMonth()===new Date().getMonth() && new Date(t.closedAt).getFullYear()===new Date().getFullYear()).reduce((a,t)=>a+t.pnl,0), wins:wins.length, losses:losses.length, count:trades.length, winRate:trades.length ? wins.length/trades.length*100 : 0, avgGain:wins.length?gain/wins.length:0, avgLoss:losses.length?loss/losses.length:0, profitFactor:loss?gain/loss:null, riskReward:losses.length && wins.length ? (gain/wins.length)/(loss/losses.length):null, drawdown};
  }
  function enter(s, side) {
    const sub=s.subscriptions.find(x=>x.active);
    if (!sub) throw Error('Activate a demo subscription first.');
    if (!s.connected || !sub.enabled) throw Error('Connect the demo broker and enable simulated trading in settings.');
    if (s.positions.length) throw Error('Close the open position before opening another position.');
    if (s.orders.filter(o=>o.status==='Filled' && !o.closing && today(o.date)).length >= sub.maxTrades) throw Error('Maximum daily trades reached.');
    if (metrics(s).today <= -sub.maxLoss) throw Error('Maximum daily loss reached.');
    const qty=0.001;
    const price=currentPrice();
    if (qty*price*RATE > sub.capital) throw Error('Insufficient allocated demo capital for 0.001 BTC.');
    const id='DEMO-'+(++s.counter), date=now();
    const position={id,strategy:sub.name,symbol:'BTCUSD',side,qty,entry:price,stop:null,target:null,status:'Open',date};
    s.positions.push(position); s.orders.push({...position,status:'Filled'}); return position;
  }
  function close(s,id,exit=currentPrice()) {
    const index=s.positions.findIndex(p=>p.id===id); if(index<0) throw Error('Position not found.');
    const p=s.positions.splice(index,1)[0], result={...p,exit,pnl:pnl(p.side,p.entry,exit,p.qty),status:'Closed',closedAt:now()};
    s.closed.push(result); s.orders.push({...p,id:'DEMO-'+(++s.counter),side:p.side==='Buy'?'Sell':'Buy',entry:exit,status:'Filled',closing:true,date:result.closedAt}); return result;
  }
  root.GJSim={RATE,get PRICE(){return currentPrice()},KEY,seed,load,save,reset,pnl,metrics,enter,close,today};
  if (typeof module !== 'undefined') module.exports=root.GJSim;
})(typeof window !== 'undefined' ? window : globalThis);
