(() => {
  const csrf = document.querySelector('meta[name="shark-csrf"]').content;
  const status = document.getElementById('shark-status');
  const result = document.getElementById('shark-result');
  const request = async (path, data = {}) => {
    const response = await fetch('/local/shark/' + path, {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':csrf}, body:JSON.stringify(data), cache:'no-store'});
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || 'Request failed.');
    return payload;
  };
  const activity = document.getElementById('shark-activity');
  if (activity) {
    const activityStatus = document.getElementById('shark-activity-status');
    const content = document.getElementById('shark-activity-content');
    const refresh = document.getElementById('shark-refresh');
    let busy = false;
    function showTable(target, rows, columns, empty) {
      const container = document.getElementById(target);
      container.replaceChildren();
      if (!rows.length) { const p=document.createElement('p'); p.className='muted small'; p.textContent=empty; container.appendChild(p); return; }
      const wrap=document.createElement('div'); wrap.className='table-scroll';
      const table=document.createElement('table'), head=document.createElement('thead'), body=document.createElement('tbody'), heading=document.createElement('tr');
      columns.forEach(([label])=>{const th=document.createElement('th');th.textContent=label;heading.appendChild(th)}); head.appendChild(heading);
      rows.forEach(row=>{const tr=document.createElement('tr');columns.forEach(([,key])=>{const td=document.createElement('td');td.textContent=row[key] || '—';tr.appendChild(td)});body.appendChild(tr)});
      table.append(head,body);wrap.appendChild(table);container.appendChild(wrap);
    }
    async function update() {
      if (busy) return; busy=true;refresh.disabled=true;
      try {
        const data=await request('activity');
        showTable('shark-open-orders',data.orders,[['ORDER ID','clientOrderId'],['SYMBOL','symbol'],['SIDE','side'],['TYPE','type'],['QUANTITY (BTC)','orderAmount'],['FILLED (BTC)','filledAmount'],['PRICE (USDT)','price'],['TIME','time']],'No open BTCUSDT orders reported.');
        showTable('shark-trades',data.trades,[['TRADE ID','id'],['ORDER ID','clientOrderId'],['SYMBOL','symbol'],['SIDE','side'],['TYPE','type'],['QUANTITY (BTC)','quantity'],['PRICE (USDT)','price'],['TIME','time']],'No recent BTCUSDT executions reported.');
        showTable('shark-order-history',data.history,[['ORDER ID','clientOrderId'],['SYMBOL','symbol'],['SIDE','side'],['TYPE','type'],['STATUS','status'],['FILLED (BTC)','executedQty'],['PRICE (USDT)','price'],['UPDATED','updatedAt']],'No recent BTCUSDT orders reported.');
        showTable('shark-positions',data.positions,[['POSITION ID','positionId'],['SYMBOL','contractPair'],['POSITION','positionType'],['QUANTITY (BTC)','quantity'],['ENTRY PRICE (USDT)','entryPrice'],['STATUS','positionStatus'],['TIME','createdTime']],'No open BTCUSDT positions reported.');
        content.hidden=false;activityStatus.textContent='Last refreshed '+new Date().toLocaleTimeString()+'. Read-only Shark account data.';
      } catch(error) {content.hidden=true;activityStatus.textContent=error.message+' Displayed data may be unavailable; check Shark directly.';}
      finally {busy=false;refresh.disabled=false;}
    }
    refresh.addEventListener('click',update);update();
    setInterval(()=>{if(!document.hidden)update()},30000);
  }
  const showStatus = async () => {
    try { const data=await request('status'); status.textContent=data.connected ? 'Credentials saved in Keychain ('+data.hint+'). Connection was verified when saved.' : 'Not connected to Shark. Connect on the subscription page.'; const availability=document.getElementById('shark-availability'); if (availability) availability.textContent=data.enabled ? 'Live submission is locally enabled. Review each order carefully before confirming.' : 'Live submission disabled: explicit local trading configuration required.'; }
    catch(e){ status.textContent=e.message; }
  };
  if (status) showStatus();
  const connect=document.getElementById('shark-connect');
  if (connect) {
    connect.addEventListener('submit',async e=>{
      e.preventDefault();
      const key=connect.elements.key.value, secret=connect.elements.secret.value;
      connect.reset();
      status.textContent='Verifying read-only connection…';
      try {const data=await request('connect',{key,secret});status.textContent=data.message;}
      catch(error){status.textContent=error.message;}
    });
    document.getElementById('shark-disconnect').addEventListener('click',async()=>{try {const data=await request('disconnect');status.textContent=data.message;}catch(e){status.textContent=e.message;}});
  }
  const form=document.getElementById('shark-order');
  if (!form) return;
  const preview=document.getElementById('shark-preview'), confirm=document.getElementById('shark-confirm'), submit=document.getElementById('shark-submit');
  let token=null, enabled=false;
  function invalidate(){token=null;enabled=false;preview.hidden=true;confirm.checked=false;submit.disabled=true;document.getElementById('limit-label').hidden=form.elements.type.value!=='LIMIT';form.elements.price.required=form.elements.type.value==='LIMIT';const review=document.getElementById('shark-review');const isBuy=form.elements.side.value==='BUY';review.textContent=isBuy?'Review Buy / Long BTC':'Review Sell / Short BTC';review.classList.toggle('buy',isBuy);review.classList.toggle('sell',!isBuy);}
  form.addEventListener('input',invalidate);form.addEventListener('change',invalidate);invalidate();
  form.addEventListener('submit',async e=>{
    e.preventDefault();invalidate();result.textContent='Preparing preview…';
    try {
      const data=await request('preview',{side:form.elements.side.value,type:form.elements.type.value,quantity:form.elements.quantity.value,price:form.elements.price.value});
      token=data.token;enabled=data.enabled;const p=data.preview;
      document.getElementById('shark-preview-details').textContent=`${data.intent==='REDUCE' ? 'REDUCE existing '+data.position.direction+' position '+data.position.positionId+' (current size '+data.position.quantity+' BTC; reduce-only)' : 'OPEN a new '+(p.side==='BUY'?'LONG':'SHORT')+' position'} · ${p.symbol} · ${p.side} · ${p.quantity} BTC · ${p.type} · Margin ${data.margin_asset || 'not configured'} · ${p.type==='LIMIT' ? 'Limit '+p.price+' USDT' : 'Recent Shark last price '+data.market_estimate+' USDT (estimate only; execution price may differ)'}`;
      document.getElementById('shark-gate').textContent=enabled?'The app will recheck the exact position and open orders before submission.':'Live submission disabled. Explicit local configuration is required.';
      preview.hidden=false;result.textContent='';
    } catch(error){result.textContent=error.message;}
  });
  confirm.addEventListener('change',()=>{submit.disabled=!(confirm.checked&&token&&enabled)});
  submit.addEventListener('click',async()=>{
    if (!token || !confirm.checked || !enabled) return;
    const once=token;invalidate();result.textContent='Submitting once. Do not retry until you check Shark.';
    try {const data=await request('submit',{token:once,confirmed:true});result.textContent=`Order ${data.order_id}: ${data.status}`;}
    catch(error){result.textContent=error.message;}
  });
})();
