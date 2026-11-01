(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  let metrics = JSON.parse($('dashboard-data').textContent);
  let series = 'all', sampleIndex = 0, refreshing = false;
  const number = value => new Intl.NumberFormat('en-US').format(value || 0);
  const compact = value => new Intl.NumberFormat('en-US', {notation:'compact', maximumFractionDigits:1}).format(value || 0);
  const percent = value => value == null ? '—' : `${value}%`;
  const names = {standard:'Standard content', greeting:'Greetings', email_reply:'Email replies', other:'Other requests'};
  const icons = {standard:'file', greeting:'spark', email_reply:'mail'};
  const text = (id, value) => { $(id).textContent = value; };
  const escape = value => String(value == null ? '' : value).replace(/[&<>"']/g, char => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[char]));
  const icon = name => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
  const date = (value, options) => new Intl.DateTimeFormat('en-US', {timeZone:metrics.reporting_timezone || 'UTC', ...options}).format(new Date(value));
  const shortDate = value => date(`${value}T12:00:00Z`, {month:'short',day:'numeric',timeZone:'UTC'});
  const status = value => ['completed','running','pending','failed','stopped','paused'].includes(value) ? value : 'unknown';
  const ratio = (value, total) => total ? Math.max(0, Math.min(100, value * 100 / total)) : 0;
  const jobURL = id => `/admin/contents/generationjob/${Number(id)}/change/`;
  const contentURL = id => `/admin/contents/greeting/${Number(id)}/change/`;

  function renderChart() {
    const counts = series === 'greetings' ? metrics.daily_greeting_counts : metrics.daily_counts;
    const labels = metrics.daily_labels;
    const total = counts.reduce((sum, count) => sum + count, 0);
    text('production-total', number(total));
    text('daily-average', number(Math.round(total / labels.length)));
    text('chart-series-label', series === 'greetings' ? 'Greetings' : 'All content');
    text('period-range', `· ${shortDate(labels[0])} – ${shortDate(labels[labels.length-1])}`);
    document.querySelectorAll('[data-series]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.series === series)));
    const maxValue = Math.max(1, ...counts);
    const power = Math.pow(10, Math.floor(Math.log10(maxValue)));
    const max = Math.ceil(maxValue / power / 2) * power * 2;
    const chartWidth = Math.max(280, $('chart-container').clientWidth);
    $('production-chart').setAttribute('viewBox', `0 0 ${chartWidth} 220`);
    const left = 38, right = chartWidth-14, top = 12, bottom = 188, step = (right-left)/labels.length;
    let svg = '';
    for (let tick = 0; tick <= 4; tick++) {
      const y = bottom - tick / 4 * (bottom-top);
      svg += `<line class="chart-grid" x1="${left}" y1="${y}" x2="${right}" y2="${y}"/><text class="chart-axis" x="${left-10}" y="${y+3}" text-anchor="end">${escape(compact(max*tick/4))}</text>`;
    }
    counts.forEach((count,index) => {
      const width = Math.min(48,step*.62), x = left + index*step + (step-width)/2;
      const height = count/max*(bottom-top);
      const label = `${shortDate(labels[index])}: ${number(count)} ${series === 'greetings' ? 'greetings' : 'outputs'}`;
      svg += `<rect class="chart-bar-secondary" x="${x}" y="${bottom-2}" width="${width}" height="2" rx="1"/><rect class="chart-bar" data-index="${index}" x="${x}" y="${bottom-Math.max(height,2)}" width="${width}" height="${Math.max(height,2)}" rx="3" tabindex="0" role="img" aria-label="${escape(label)}"><title>${escape(label)}</title></rect>`;
      if(labels.length <= 7 || index % 5 === 0 || index === labels.length-1) {
        svg += `<text class="chart-axis" x="${x+width/2}" y="210" text-anchor="middle">${escape(shortDate(labels[index]))}</text>`;
      }
    });
    $('production-chart').innerHTML = svg;
    $('production-chart').setAttribute('aria-label', `${series === 'greetings' ? 'Greetings' : 'All content'} saved over ${metrics.period_days} days. ${number(total)} total. Daily values are available below.`);
    $('chart-table').innerHTML = `<table><thead><tr><th>Date</th><th>All content</th><th>Greetings</th></tr></thead><tbody>${labels.map((day,index)=>`<tr><td>${escape(day)}</td><td>${number(metrics.daily_counts[index])}</td><td>${number(metrics.daily_greeting_counts[index])}</td></tr>`).join('')}</tbody></table>`;
    $('chart-tooltip').hidden = true;
  }

  function renderSample() {
    const samples = metrics.greeting_samples;
    if(!samples.length) {
      text('sample-text','Your saved greetings will appear here.'); text('sample-language','No samples yet'); text('sample-position','');
      $('sample-link').removeAttribute('href'); text('sample-link','Saved greeting');
      $('next-sample').disabled = true; $('copy-sample').disabled = true; return;
    }
    sampleIndex %= samples.length;
    const sample = samples[sampleIndex];
    text('sample-text',sample.generated_content);
    $('sample-text').lang = sample.language__code || '';
    text('sample-language',sample.language__name || 'Greeting');
    text('sample-position', `${sampleIndex+1} / ${samples.length}`);
    text('sample-link', `Greeting #${sample.id} · ${date(sample.created_at,{month:'short',day:'numeric'})}`);
    $('sample-link').href = contentURL(sample.id);
    $('next-sample').disabled = samples.length < 2; $('copy-sample').disabled = false;
  }

  function render() {
    const m = metrics, u = m.usage;
    document.querySelectorAll('[data-days]').forEach(button=>button.setAttribute('aria-pressed',String(Number(button.dataset.days) === m.period_days)));
    document.querySelectorAll('.period-caption').forEach(item=>item.textContent = `over ${m.period_days} days`);
    text('timezone',m.reporting_timezone);
    text('greeting-today',number(m.greeting_today));
    text('daily-goal-caption', m.greeting_target ? `of ${number(m.greeting_target)} daily target` : 'No daily target set');
    $('goal-mini').style.width = `${m.greeting_target_progress}%`;
    text('acceptance',percent(m.greeting_success_rate));
    $('acceptance').title = 'Saved greetings / (saved + skipped) for runs created in the selected period.';
    text('skip-count',`${number(m.greeting_skipped)} skipped`);
    text('duplicate-count',number(m.greeting_duplicates)); text('invalid-count',number(m.greeting_invalid));
    $('skip-count').title = `${number(m.greeting_duplicates)} duplicates · ${number(m.greeting_invalid)} failed attempts. Details are in the generation logs.`;
    text('token-total',compact(u.tokens)); $('token-total').title = `${number(u.tokens)} tokens`;
    text('request-count',`${number(u.requests)} requests`);
    text('estimated-cost', u.estimated_cost == null ? '—' : new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',minimumFractionDigits:4,maximumFractionDigits:4}).format(u.estimated_cost));
    $('estimated-cost').title = u.unpriced_requests ? 'Estimate unavailable: some recorded models have no configured price.' : 'Estimated from recorded input, cached input and output tokens at Standard pricing. Excludes unrecorded usage and account adjustments.';
    text('library-total',number(m.content_total));
    text('goal-percent',m.greeting_target ? `${m.greeting_target_progress}%` : '—');
    $('goal-progress').style.width = `${m.greeting_target_progress}%`;
    text('goal-numbers',m.greeting_target ? `${number(m.greeting_today)} / ${number(m.greeting_target)} greetings` : `${number(m.greeting_today)} greetings today`);
    text('schedule-badge',m.greeting_schedule_enabled ? 'Daily schedule on' : 'Schedule off');
    const latest = m.latest_greeting;
    $('latest-link').hidden = !latest;
    $('latest-status').className = `status-pill ${status(latest?.status)}`;
    text('latest-status',latest ? latest.status : 'No runs');
    text('latest-result',latest ? `${number(latest.generated_count)} saved · ${number(latest.skipped_count)} skipped · ${percent(latest.acceptance)} accepted` : 'Create a job to start your first run.');
    if(latest) $('latest-link').href = jobURL(latest.id);
    text('active-jobs',`${m.running_jobs} active`);
    text('queue-status',`${number(m.pending_jobs)} pending · ${number(m.total_jobs)} runs all time`);
    $('jobs-body').innerHTML = m.recent_jobs.length ? m.recent_jobs.map(job=>`<tr><td><a class="run-cell" href="${jobURL(job.id)}"><span class="run-icon">${icon(icons[job.generation_type] || 'jobs')}</span><span><strong>${escape(names[job.generation_type] || job.generation_type)}</strong><small>RUN #${Number(job.id)}</small></span></a></td><td><span class="status-pill ${status(job.status)}">${escape(job.status)}</span></td><td>${number(job.generated_count)} <span style="color:var(--muted)">/ ${number(job.count)}</span><div class="mini-progress"><span style="width:${ratio(job.generated_count,job.count)}%"></span></div></td><td class="${job.skipped_count ? 'skip-warning' : ''}">${number(job.skipped_count)}</td><td>${escape(date(job.created_at,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}))}</td></tr>`).join('') : '<tr><td colspan="5" class="empty-state">No generation runs yet. Create a job to get started.</td></tr>';
    text('usage-total',compact(u.tokens)); text('input-tokens',compact(u.input)); text('output-tokens',compact(u.output));
    $('token-split').innerHTML = `<span style="width:${ratio(u.input,u.tokens)}%"></span><span style="width:${ratio(u.output,u.tokens)}%"></span>`;
    $('usage-types').innerHTML = u.by_type.length ? [...u.by_type].sort((a,b)=>b.tokens-a.tokens).map(item=>`<div class="usage-type"><div><span>${escape(names[item.type] || item.type)} <small>${number(item.requests)} calls</small></span><b>${compact(item.tokens)}</b></div><div class="usage-type-track"><span style="width:${ratio(item.tokens,u.tokens)}%"></span></div></div>`).join('') : '<div class="empty-state">No recorded usage in this period.</div>';
    let usageNote = u.first_seen ? `Records shown from ${date(u.first_seen,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false})} (${m.reporting_timezone}). ` : 'Usage appears after generation. ';
    usageNote += u.unpriced_requests ? 'Cost unavailable for some models. ' : 'Estimate uses Standard pricing. ';
    usageNote += 'Not your account invoice.';
    if(u.cached) usageNote += ` ${number(u.cached)} cached input tokens included.`;
    text('usage-note',usageNote);
    text('attention-count',`${m.attention_total} issues`);
    text('delivery-success',percent(m.delivery_success_rate)); text('delivery-pending',number(m.delivery_pending)); text('greeting-clients',number(m.recipient_counts.greeting));
    const alerts = [...m.recent_failed_jobs.map(job=>`<div class="alert-item"><span>Failed ${escape(names[job.generation_type] || 'generation')} #${Number(job.id)}</span><a href="${jobURL(job.id)}">Review ↗</a></div>`), ...m.recent_failed_deliveries.map(item=>`<div class="alert-item"><span>Delivery #${Number(item.id)} · ${escape(item.client__name)}</span><a href="/admin/contents/contentdelivery/${Number(item.id)}/change/">Review ↗</a></div>`)];
    $('alerts').innerHTML = alerts.length ? alerts.join('') : `<div class="alerts-clear">${icon('check')}<span>No failed jobs or deliveries in this period.</span></div>`;
    text('model-name',m.model_name);
    text('updated-time',`Snapshot ${date(m.updated_at,{hour:'2-digit',minute:'2-digit',hour12:false})} ${m.reporting_timezone} · Refreshes every minute`);
    renderChart(); renderSample();
  }

  async function refresh(days = metrics.period_days) {
    if(refreshing) return;
    refreshing = true;
    $('refresh').disabled = true;
    document.querySelectorAll('[data-days]').forEach(button=>button.disabled = true);
    text('sync-text','Refreshing…');
    const controller = new AbortController();
    const timer = setTimeout(()=>controller.abort(),10000);
    try {
      const response = await fetch(`${document.body.dataset.metricsUrl}?days=${days}`,{credentials:'same-origin',cache:'no-store',signal:controller.signal,headers:{Accept:'application/json'}});
      if(!response.ok || !response.headers.get('content-type')?.includes('application/json')) throw new Error('Session or network unavailable');
      const fresh = await response.json();
      if(!Array.isArray(fresh.daily_counts) || !fresh.usage) throw new Error('Invalid metrics');
      metrics = fresh; render();
      $('refresh-error').hidden = true; $('sync-status').classList.remove('stale'); text('sync-text','Snapshot updated');
      const url = new URL(window.location.href); url.searchParams.set('days',String(metrics.period_days)); history.replaceState(null,'',url);
    } catch(error) {
      text('sync-text','Update unavailable'); $('sync-status').classList.add('stale');
      text('refresh-error','Could not refresh. The last successful snapshot is still shown. Check your connection or sign in again, then refresh.'); $('refresh-error').hidden = false;
    } finally {
      clearTimeout(timer); refreshing = false; $('refresh').disabled = false;
      document.querySelectorAll('[data-days]').forEach(button=>button.disabled = false);
    }
  }

  $('refresh').addEventListener('click',()=>refresh());
  document.querySelectorAll('[data-days]').forEach(button=>button.addEventListener('click',()=>refresh(Number(button.dataset.days))));
  document.querySelectorAll('[data-series]').forEach(button=>button.addEventListener('click',()=>{series=button.dataset.series;renderChart();}));
  $('next-sample').addEventListener('click',()=>{sampleIndex++;renderSample();});
  $('copy-sample').addEventListener('click',async()=>{
    try {await navigator.clipboard.writeText(metrics.greeting_samples[sampleIndex].generated_content);text('copy-status','Greeting copied.');$('copy-sample').innerHTML=icon('check');setTimeout(()=>$('copy-sample').innerHTML=icon('copy'),1600);}
    catch(error){text('copy-status','Copy unavailable. Select the greeting text to copy it manually.');text('sample-position','Select text to copy');}
  });
  const showTip = target => {
    const bar = target.closest('[data-index]'); if(!bar) return;
    text('chart-tooltip',bar.getAttribute('aria-label')); $('chart-tooltip').hidden=false;
  };
  $('production-chart').addEventListener('pointerover',event=>showTip(event.target));
  $('production-chart').addEventListener('focusin',event=>showTip(event.target));
  $('production-chart').addEventListener('pointerleave',()=>$('chart-tooltip').hidden=true);
  $('production-chart').addEventListener('focusout',()=>$('chart-tooltip').hidden=true);
  $('theme-select').value=document.documentElement.dataset.theme || 'auto';
  $('theme-select').addEventListener('change',event=>{document.documentElement.dataset.theme=event.target.value;try{localStorage.setItem('theme',event.target.value);}catch(error){/* Theme still applies for this page. */}});
  new MutationObserver(()=>$('theme-select').value=document.documentElement.dataset.theme || 'auto').observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});
  const mobile = window.matchMedia('(max-width:820px)');
  function syncMenu(){ $('sidebar').inert = mobile.matches && !$('sidebar').classList.contains('open'); }
  function closeMenu(){ $('sidebar').classList.remove('open');$('nav-overlay').hidden=true;$('menu-toggle').setAttribute('aria-expanded','false');syncMenu(); }
  mobile.addEventListener('change',closeMenu);syncMenu();
  $('menu-toggle').addEventListener('click',()=>{const open=$('sidebar').classList.toggle('open');$('nav-overlay').hidden=!open;$('menu-toggle').setAttribute('aria-expanded',String(open));syncMenu();});
  $('nav-overlay').addEventListener('click',closeMenu);
  document.addEventListener('keydown',event=>{if(event.key==='Escape'){closeMenu();$('chart-tooltip').hidden=true;}});
  setInterval(()=>{if(!document.hidden) refresh();},60000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden && Date.now()-new Date(metrics.updated_at).getTime()>60000) refresh();});
  let chartWidth = 0;
  new ResizeObserver(entries=>{const width = entries[0].contentRect.width;if(width !== chartWidth){chartWidth=width;renderChart();}}).observe($('chart-container'));
  render();
})();
