(() => {
    'use strict';
    const filters = document.getElementById('changelist-filter');
    if (!filters || !document.body.classList.contains('model-generationjob')) return;
    const groups = Array.from(filters.querySelectorAll('details'));
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
