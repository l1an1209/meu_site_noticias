(function () {
    const shell = document.getElementById('appShell');
    const KEY = 'app-sidebar-collapsed';

    if (shell && localStorage.getItem(KEY) === '1' && window.matchMedia('(min-width: 992px)').matches) {
        shell.classList.add('is-collapsed');
    }

    document.getElementById('appNavToggle')?.addEventListener('click', () => {
        shell?.classList.toggle('nav-open');
    });
    document.getElementById('appNavBackdrop')?.addEventListener('click', () => {
        shell?.classList.remove('nav-open');
    });
    document.getElementById('appSidebarCollapse')?.addEventListener('click', () => {
        if (!shell) return;
        shell.classList.toggle('is-collapsed');
        localStorage.setItem(KEY, shell.classList.contains('is-collapsed') ? '1' : '0');
    });

    document.querySelectorAll('.js-loading-form').forEach((form) => {
        form.addEventListener('submit', () => {
            form.querySelectorAll('[type="submit"]').forEach((btn) => {
                btn.disabled = true;
                btn.dataset.label = btn.textContent;
                btn.textContent = btn.dataset.loading || 'Salvando…';
            });
        });
    });

    document.querySelectorAll('input[type="file"][accept*="image"]:not([multiple])').forEach((input) => {
        input.addEventListener('change', () => {
            const file = input.files && input.files[0];
            if (!file) return;
            const box = input.closest('.upload-row, .d-flex, .mb-3')?.querySelector('.preview-box');
            if (!box) return;
            const url = URL.createObjectURL(file);
            box.innerHTML = `<img src="${url}" alt="">`;
        });
    });

    document.querySelectorAll('input[type="file"][multiple]').forEach((input) => {
        input.addEventListener('change', () => {
            const host = document.getElementById('galeriaPreview');
            if (!host) return;
            host.innerHTML = '';
            Array.from(input.files || []).forEach((file) => {
                const url = URL.createObjectURL(file);
                const img = document.createElement('img');
                img.src = url;
                img.alt = file.name;
                img.style.width = '88px';
                img.style.height = '64px';
                img.style.objectFit = 'cover';
                img.style.borderRadius = '8px';
                host.appendChild(img);
            });
        });
    });
})();
