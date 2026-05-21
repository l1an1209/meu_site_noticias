(function () {
    const cfg = window.JIPA_CONFIG || {};
    const horaEl = document.getElementById('horaLocal');
    const localEl = document.getElementById('localText');
    const coordsEl = document.getElementById('coordsText');
    const climaEl = document.getElementById('climaText');
    const climaDet = document.getElementById('climaDetalhe');
    const climaIcon = document.getElementById('climaIcon');
    const btnGeo = document.getElementById('btnGeo');
    const logoWrap = document.getElementById('logoWrap');

    const climaMap = {
        0: { icon: 'fa-sun', txt: 'Céu limpo' },
        1: { icon: 'fa-cloud-sun', txt: 'Parcialmente nublado' },
        2: { icon: 'fa-cloud', txt: 'Nublado' },
        3: { icon: 'fa-cloud', txt: 'Nublado' },
        61: { icon: 'fa-cloud-rain', txt: 'Chuva' },
        63: { icon: 'fa-cloud-showers-heavy', txt: 'Chuva moderada' },
        95: { icon: 'fa-bolt', txt: 'Tempestade' },
    };

    function atualizarRelogio() {
        const agora = new Date();
        horaEl.textContent = agora.toLocaleTimeString('pt-BR', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
        });
    }

    async function carregarClima(lat, lon) {
        climaEl.textContent = 'Carregando...';
        try {
            const url = `${cfg.climaUrl}?lat=${lat}&lon=${lon}`;
            const res = await fetch(url);
            const data = await res.json();
            if (data.ok) {
                const info = climaMap[data.codigo] || { icon: 'fa-cloud-sun', txt: 'Variável' };
                climaIcon.className = `fas ${info.icon}`;
                climaEl.textContent = `${Math.round(data.temperatura)}°C`;
                climaDet.textContent = `${info.txt} · Umidade ${data.umidade}% · Sensação ${Math.round(data.sensacao)}°C`;
            } else {
                climaEl.textContent = 'Indisponível';
            }
        } catch {
            climaEl.textContent = 'Sem conexão';
        }
    }

    function definirCoords(lat, lon, label) {
        coordsEl.textContent = `${lat.toFixed(4)}, ${lon.toFixed(4)}`;
        if (label) localEl.textContent = label;
        carregarClima(lat, lon);
    }

    btnGeo?.addEventListener('click', () => {
        if (!navigator.geolocation) {
            alert('Geolocalização não suportada neste dispositivo.');
            return;
        }
        btnGeo.disabled = true;
        btnGeo.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i> Localizando...';
        navigator.geolocation.getCurrentPosition(
            (pos) => {
                definirCoords(pos.coords.latitude, pos.coords.longitude, 'Sua localização');
                btnGeo.innerHTML = '<i class="fas fa-check me-1"></i> Localização ativa';
            },
            () => {
                definirCoords(cfg.latPadrao, cfg.lonPadrao, cfg.cidade + ', RO');
                btnGeo.disabled = false;
                btnGeo.innerHTML = '<i class="fas fa-crosshairs me-1"></i> Usar minha localização';
                alert('Permita localização ou usamos Ji-Paraná como padrão.');
            },
            { enableHighAccuracy: true, timeout: 12000 }
        );
    });

    logoWrap?.addEventListener('click', () => {
        logoWrap.style.animation = 'none';
        void logoWrap.offsetWidth;
        logoWrap.querySelector('.exp-logo').style.animation = 'logo-spin 0.8s ease';
        setTimeout(() => {
            logoWrap.querySelector('.exp-logo').style.animation = 'logo-float 3s ease-in-out infinite';
        }, 800);
    });

    const style = document.createElement('style');
    style.textContent = '@keyframes logo-spin { from{transform:rotate(0)} to{transform:rotate(360deg)} }';
    document.head.appendChild(style);

    atualizarRelogio();
    setInterval(atualizarRelogio, 1000);
    definirCoords(cfg.latPadrao, cfg.lonPadrao, cfg.cidade + ', RO');

    sessionStorage.setItem('jiparana_experiencia_vista', '1');
})();
