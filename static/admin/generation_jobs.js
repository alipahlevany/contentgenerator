(() => {
    'use strict';
    const filters = document.getElementById('changelist-filter');
    if (!filters || !document.body.classList.contains('model-generationjob')) return;
    const groups = Array.from(filters.querySelectorAll('details'));
    const slot = document.getElementById('cg-job-filter-slot');
    if (slot) slot.append(filters);
    const search = document.getElementById('searchbar');
    if (search) search.placeholder = 'Search runs…';
    const labels = {'generation type':'Type', status:'Status', 'created at':'Date'};
    const placeMenu = group => {
        const menu = group.querySelector('ul');
        if (!group.open || !menu) return;
        menu.style.left = '0px';
        const box = menu.getBoundingClientRect();
        const offset = Math.max(16 - box.left, Math.min(0, document.documentElement.clientWidth - 16 - box.right));
        menu.style.left = `${offset}px`;
    };
    groups.forEach(group => {
        const summary = group.querySelector('summary');
        const selected = group.querySelector('li.selected a');
        const label = labels[group.dataset.filterTitle] || group.dataset.filterTitle;
        group.open = false;
        if (summary && selected) {
            summary.textContent = `${label}: `;
            const value = document.createElement('strong');
            value.textContent = selected.textContent.trim();
            summary.append(value);
            summary.setAttribute('aria-label', `Filter ${label.toLowerCase()}: ${value.textContent}`);
            group.classList.toggle('is-filtered', selected.parentElement !== group.querySelector('li'));
        }
        group.addEventListener('toggle', () => {
            if (group.open) {
                groups.forEach(other => { if (other !== group) other.open = false; });
                placeMenu(group);
            }
        });
    });
    filters.classList.add('cg-job-filters');
    window.addEventListener('resize', () => groups.forEach(placeMenu));
    document.addEventListener('click', event => {
        if (!filters.contains(event.target)) groups.forEach(group => { group.open = false; });
    });
    document.addEventListener('keydown', event => {
        if (event.key !== 'Escape') return;
        const open = groups.find(group => group.open);
        if (open) { open.open = false; open.querySelector('summary').focus(); }
    });
})();

// Refresh only progress cells; keep filters, selections and unsaved edits intact.
(() => {
    'use strict';
    const markers = [...document.querySelectorAll('[data-job-id][data-progress-url]')];
    if (!markers.length) return;
    const ids = [...new Set(markers.map(node => node.dataset.jobId))];
    const url = new URL(markers[0].dataset.progressUrl, window.location.origin);
    url.searchParams.set('ids', ids.join(','));
    const indicator = document.createElement('p');
    indicator.setAttribute('role', 'status');
    indicator.textContent = 'Live updates connecting…';
    (document.querySelector('.cg-jobs-heading') || document.querySelector('#content')).append(indicator);
    let timer;
    let busy = false;
    let failures = 0;
    let stopped = false;
    const update = async () => {
        clearTimeout(timer);
        if (busy || stopped || document.hidden) return;
        busy = true;
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 10000);
        try {
            const response = await fetch(url, {
                credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
                headers: {'Accept': 'application/json'},
            });
            if (response.redirected || response.status === 401 || response.status === 403) {
                stopped = true;
                throw new Error('session');
            }
            if (!response.ok) throw new Error('network');
            const data = await response.json();
            for (const job of data.jobs) {
                const marker = document.querySelector(`[data-job-id="${job.id}"]`);
                if (!marker) continue;
                const row = marker.closest('tr');
                for (const [field, html] of Object.entries(job.html)) {
                    const cell = row ? row.querySelector(`.field-${field}`)
                        : document.querySelector(`.field-${field} .readonly`);
                    if (cell && cell.innerHTML !== html) cell.innerHTML = html;
                }
                if (!row) for (const [field, value] of Object.entries(job.values)) {
                    const cell = document.querySelector(`.field-${field} .readonly`);
                    if (cell) cell.textContent = value === null ? '—' : String(value);
                }
            }
            failures = 0;
            indicator.textContent = `Live · Updated ${new Date().toLocaleTimeString()}`;
        } catch (_) {
            failures += 1;
            indicator.textContent = stopped ? 'Live updates paused. Sign in again.' : 'Connection interrupted · Retrying…';
        } finally {
            clearTimeout(timeout);
            busy = false;
            if (!stopped && !document.hidden) timer = setTimeout(update, Math.min(30000, 3000 * 2 ** Math.min(failures, 4)));
        }
    };
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) clearTimeout(timer);
        else update();
    });
    window.addEventListener('pagehide', () => { stopped = true; clearTimeout(timer); });
    window.addEventListener('pageshow', event => { if (event.persisted) { stopped = false; update(); } });
    update();
})();
