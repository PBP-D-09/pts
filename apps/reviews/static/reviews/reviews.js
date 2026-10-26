(() => {
    const root = document.querySelector('[data-reviews]');
    if (!root) return;
    const dialog = document.querySelector('#reviews-dialog');
    const content = document.querySelector('#reviews-dialog-content');
    const results = document.querySelector('#reviews-results');
    const error = document.querySelector('#reviews-error');
    const loading = document.querySelector('#reviews-loading');
    const headers = {
        'X-Reviews-Request': 'true'
    };
    let currentURL = new URL(location.href);
    let retry = null;
    let listController = null;
    let previewURL = null;
    let modalBusy = false;
    let returnFocus = null;

    function showError(action) {
        retry = action;
        error.hidden = false;
    }

    function loginPrompt() {
        content.replaceChildren(document.querySelector('#reviews-login-prompt').content.cloneNode(true));
        dialog.classList.add('reviews-dialog-small');
        returnFocus = document.activeElement;
        if (!dialog.open) dialog.showModal();
    }
    async function loadReviews(url, append = false) {
        listController?.abort();
        const controller = new AbortController();
        listController = controller;
        error.hidden = true;
        results.setAttribute('aria-busy', 'true');
        if (!append) {
            results.hidden = true;
            loading.hidden = false;
        }
        const more = results.querySelector('[data-load-more]');
        if (append && more) {
            more.textContent = 'Loading…';
            more.setAttribute('aria-disabled', 'true');
        }
        try {
            const response = await fetch(url, {
                headers,
                signal: controller.signal
            });
            if (!response.ok) throw new Error('Request failed');
            const html = await response.text();
            if (append) {
                const parsed = new DOMParser().parseFromString(html, 'text/html');
                const cards = parsed.querySelector('#review-list');
                if (!cards) throw new Error('Invalid response');
                results.querySelector('#review-list').append(...cards.children);
                results.querySelector('#reviews-pagination').replaceWith(parsed.querySelector('#reviews-pagination'));
                const status = results.querySelector('.reviews-status span');
                if (status) status.textContent = `Showing ${results.querySelectorAll('.reviews-card').length} reviews`;
            } else {
                results.innerHTML = html;
                const total = Number(results.querySelector('[data-review-total]').dataset.reviewTotal);
                root.querySelector('[data-review-heading-count]').textContent = `${total} reviews • ${total ? 'Real experiences from our community' : 'Share the first experience with this meal'}`;
                currentURL = new URL(url, location.href);
                history.replaceState({}, '', currentURL);
            }
        } catch (e) {
            if (e.name !== 'AbortError') showError(() => loadReviews(url, append));
        } finally {
            if (listController === controller) {
                results.hidden = false;
                loading.hidden = true;
                results.removeAttribute('aria-busy');
                if (more?.isConnected) {
                    more.textContent = 'Load More Reviews';
                    more.removeAttribute('aria-disabled');
                }
            }
        }
    }

    function updateStars(scope = content) {
        scope.querySelectorAll('.reviews-rating-options').forEach(group => {
            const selected = group.querySelector('input:checked');
            const value = Number(selected?.value || 0);
            const image = group.querySelector('[data-star-base]');
            image.src = image.dataset.starBase.replace('stars-0.svg', `stars-${value}.svg`);
            group.querySelectorAll('label').forEach(label => label.classList.toggle('is-filled', Number(label.querySelector('input').value) <= value));
            group.querySelector('output').textContent = value ? `${value} / 5` : 'Select 1–5 stars';
        });
    }
    async function openModal(url) {
        if (root.dataset.authenticated !== 'true') {
            loginPrompt();
            return;
        }
        returnFocus = document.activeElement;
        try {
            const response = await fetch(url, {
                headers
            });
            if (response.status === 401) {
                loginPrompt();
                return;
            }
            if (!response.ok) throw new Error('Request failed');
            content.innerHTML = await response.text();
            content.querySelector('form').action = url;
            dialog.classList.toggle('reviews-dialog-small', !!content.querySelector('[data-deleting]'));
            updateStars();
            if (!dialog.open) dialog.showModal();
        } catch {
            showError(() => openModal(url));
        }
    }

    function closeDialog() {
        if (modalBusy) return;
        dialog.close();
    }
    dialog.addEventListener('cancel', event => {
        if (modalBusy) event.preventDefault();
    });
    dialog.addEventListener('close', () => {
        if (previewURL) URL.revokeObjectURL(previewURL);
        previewURL = null;
        returnFocus?.focus();
    });
    document.querySelector('#reviews-retry').addEventListener('click', () => retry?.());
    root.addEventListener('click', event => {
        const target = event.target.closest('[data-modal],[data-close],[data-write],#write-review,[data-load-more],[data-filter-link],[data-remove-photo]');
        if (!target) return;
        event.preventDefault();
        if (target.matches('[data-close]')) closeDialog();
        else if (target.matches('[data-modal]')) openModal(target.href);
        else if (target.matches('[data-write],#write-review')) openModal(root.dataset.createUrl);
        else if (target.matches('[data-load-more]')) {
            if (!target.hasAttribute('aria-disabled')) loadReviews(target.href, true);
        } else if (target.matches('[data-filter-link]')) loadReviews(new URL(target.getAttribute('href'), currentURL));
        else if (target.matches('[data-remove-photo]')) {
            const form = target.closest('form');
            form.querySelector('input[type=file]').value = '';
            form.querySelector('[data-photo-preview]').hidden = true;
            form.querySelector('[data-remove-input]').value = 'true';
            form.querySelector('[data-upload-label]').textContent = 'Add Food Photo';
            if (previewURL) URL.revokeObjectURL(previewURL);
            previewURL = null;
        }
    });
    root.addEventListener('pointerover', event => {
        const label = event.target.closest('.reviews-rating-options label');
        if (!label) return;
        const group = label.closest('.reviews-rating-options');
        const image = group.querySelector('[data-star-base]');
        image.src = image.dataset.starBase.replace('stars-0.svg', `stars-${label.querySelector('input').value}.svg`);
    });
    root.addEventListener('pointerout', event => {
        const group = event.target.closest('.reviews-rating-options');
        if (group && !group.contains(event.relatedTarget)) updateStars();
    });
    root.addEventListener('change', event => {
        if (event.target.closest('#reviews-filters')) {
            const url = new URL(location.pathname, location.origin);
            url.search = new URLSearchParams(new FormData(event.target.form)).toString();
            loadReviews(url);
        }
        if (event.target.closest('.reviews-rating-options')) updateStars();
        if (event.target.matches('input[type=file]')) {
            const file = event.target.files[0];
            if (!file) return;
            const form = event.target.form;
            if (!['image/jpeg', 'image/png'].includes(file.type) || file.size > 5 * 1024 * 1024) {
                event.target.value = '';
                const message = form.querySelector('[data-form-error]');
                message.textContent = 'Please upload a JPG or PNG image, up to 5 MB.';
                message.hidden = false;
                return;
            }
            if (previewURL) URL.revokeObjectURL(previewURL);
            previewURL = URL.createObjectURL(file);
            form.querySelector('[data-photo-preview] img').src = previewURL;
            form.querySelector('[data-photo-preview]').hidden = false;
            form.querySelector('[data-photo-name]').textContent = file.name;
            form.querySelector('[data-upload-label]').textContent = 'Replace photo';
            form.querySelector('[data-remove-input]').value = '';
        }
    });
    root.addEventListener('input', event => {
        if (event.target.matches('textarea[name=text]')) content.querySelector('[data-character-count]').textContent = event.target.value.length;
    });
    root.addEventListener('submit', async event => {
        const form = event.target;
        if (!form.matches('[data-review-form],[data-helpful]')) return;
        event.preventDefault();
        if (form.dataset.pending) return;
        if (root.dataset.authenticated !== 'true') {
            loginPrompt();
            return;
        }
        const button = form.querySelector('[type=submit]');
        const label = button.innerHTML;
        const data = new FormData(form);
        const isHelpful = form.matches('[data-helpful]');
        form.dataset.pending = 'true';
        button.disabled = true;
        button.textContent = isHelpful ? 'Updating…' : form.matches('[data-deleting]') ? 'Deleting…' : form.action.includes('/edit/') ? 'Saving…' : 'Submitting…';
        if (!isHelpful) modalBusy = true;
        try {
            const response = await fetch(form.action, {
                method: 'POST',
                headers,
                body: data
            });
            if (response.status === 401) {
                loginPrompt();
                return;
            }
            if (response.status === 422 && !isHelpful) {
                const action = form.action;
                const oldInput = form.querySelector('input[type=file]');
                const oldPreview = form.querySelector('[data-photo-preview]');
                const oldRemove = form.querySelector('[data-remove-input]')?.value;
                content.innerHTML = await response.text();
                if (oldInput?.files.length) {
                    content.querySelector('input[type=file]').replaceWith(oldInput);
                    content.querySelector('[data-photo-preview]').replaceWith(oldPreview);
                    content.querySelector('[data-upload-label]').textContent = 'Replace photo';
                } else if (oldRemove === 'true') {
                    content.querySelector('[data-photo-preview]').hidden = true;
                    content.querySelector('[data-upload-label]').textContent = 'Add Food Photo';
                }
                content.querySelector('form').action = action;
                updateStars();
                content.querySelector('.errorlist, .ui-field__error')?.scrollIntoView({
                    block: 'nearest'
                });
                return;
            }
            if (!response.ok) throw new Error('Request failed');
            const result = await response.json();
            if (isHelpful) {
                button.innerHTML = label;
                button.querySelector('span').textContent = `Helpful ${result.count}`;
                button.setAttribute('aria-pressed', String(result.selected));
                button.classList.toggle('is-selected', result.selected);
            } else {
                modalBusy = false;
                dialog.close();
                window.showToast?.(result.message);
                const destination = new URL(result.url, location.origin);
                if (destination.pathname !== location.pathname) location.assign(destination);
                else await loadReviews(destination);
            }
        } catch {
            if (isHelpful) showError(() => form.requestSubmit());
            else {
                const message = form.querySelector('[data-form-error]');
                message.textContent = 'Something went wrong. Please try again.';
                message.hidden = false;
            }
        } finally {
            modalBusy = false;
            delete form.dataset.pending;
            button.disabled = false;
            if (!isHelpful || !button.querySelector('span')) button.innerHTML = label;
        }
    });
})();
