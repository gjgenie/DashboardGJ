const assert = require('assert');
const S = require('../static/js/simulation.js');
global.localStorage = {data:{},getItem(k){return this.data[k]||null},setItem(k,v){this.data[k]=v}};
function ready(){const s=S.seed();s.subscriptions.push({id:'time-machine',name:'GJ Crypto Time Machine',active:true,enabled:true,capital:10000,maxTrades:2,maxLoss:500,status:'Stopped'});return s;}
let s=ready(); let p=S.enter(s,'Buy');assert.equal(p.side,'Buy');assert.equal(s.orders.at(-1).status,'Filled');assert.throws(()=>S.enter(s,'Sell'),/Close/);let closed=S.close(s,p.id,p.entry+1000);assert.equal(closed.pnl,83);assert.equal(s.positions.length,0);p=S.enter(s,'Sell');assert.equal(S.close(s,p.id,p.entry-1000).pnl,83);assert.throws(()=>S.enter(s,'Buy'),/Maximum daily trades/);
s=ready();s.closed.push({pnl:-500,closedAt:new Date().toISOString()});assert.throws(()=>S.enter(s,'Buy'),/Maximum daily loss/);assert.equal(S.pnl('Sell',100,90,0.01),8.3);S.save(s);assert.equal(S.reset().subscriptions.length,0);assert.equal(S.load().closed.length,4);console.log('Simulation tests passed');
