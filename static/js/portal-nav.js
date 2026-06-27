(function () {
    const clockEl = document.getElementById('navClock');
    const tempEl = document.getElementById('navWeatherTemp');

    function updateClock() {
        if (!clockEl) return;
        const now = new Date();
        clockEl.textContent = now.toLocaleString('pt-BR', {
            weekday: 'short',
            day: '2-digit',
            month: 'short',
            hour: '2-digit',
            minute: '2-digit',
        });
    }

    updateClock();
    setInterval(updateClock, 30000);

    if (tempEl) {
        fetch('/api/clima/')
            .then((r) => r.json())
            .then((data) => {
                if (data.ok && data.temperatura != null) {
                    tempEl.textContent = Math.round(data.temperatura) + '°C';
                }
            })
            .catch(() => {});
    }
})();
