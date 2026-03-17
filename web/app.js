document.addEventListener('DOMContentLoaded', async function() {
    if (typeof LightweightCharts === 'undefined') {
        alert('图表库加载失败，请刷新页面重试！');
        document.getElementById('legend').innerText = '图表库加载失败';
        return;
    }

    const chart = LightweightCharts.createChart(document.getElementById('chart-container'), {
        layout: { textColor: '#d1d4dc', background: { type: 'solid', color: '#131722' } },
        grid: { vertLines: { color: '#363c4e' }, horzLines: { color: '#363c4e' } },
        crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
        timeScale: { timeVisible: true, secondsVisible: false }
    });

    chart.priceScale('right').applyOptions({ scaleMargins: { top: 0.1, bottom: 0.3 } });

    const series = chart.addCandlestickSeries({ upColor: '#26a69a', downColor: '#ef5350', borderVisible: false, wickUpColor: '#26a69a', wickDownColor: '#ef5350' });
    const volumeSeries = chart.addHistogramSeries({ color: '#26a69a', priceFormat: { type: 'volume' }, priceScaleId: '', scaleMargins: { top: 0.8, bottom: 0 } });

    const legend = document.getElementById('legend');
    const tzOffset = new Date().getTimezoneOffset() * 60;

    let ws = null;
    let pingInterval = null;
    let currentExchange = "binance";
    let currentSymbol = "BTC/USDT";
    let currentBar = null;

    function snapTime(timestampMs, interval) {
        const date = new Date(timestampMs);
        if (interval === '1m') return Math.floor(timestampMs / 60000) * 60;
        if (interval === '5m') return Math.floor(timestampMs / 300000) * 300;
        if (interval === '15m') return Math.floor(timestampMs / 900000) * 900;
        if (interval === '1h') { date.setUTCMinutes(0, 0, 0); return Math.floor(date.getTime() / 1000); }
        if (interval === '4h') { date.setUTCHours(Math.floor(date.getUTCHours() / 4) * 4, 0, 0, 0); return Math.floor(date.getTime() / 1000); }
        if (interval === '1d') { date.setUTCHours(0, 0, 0, 0); return Math.floor(date.getTime() / 1000); }
        return Math.floor(timestampMs / 1000);
    }

    async function loadSymbols() {
        try {
            const res = await fetch('/api/symbols');
            const data = await res.json();
            const datalist = document.getElementById('symbol-list');
            datalist.innerHTML = '';

            for (const exchange in data) {
                data[exchange].forEach(sym => {
                    const option = document.createElement('option');
                    option.value = `${exchange}:${sym}`;
                    datalist.appendChild(option);
                });
            }
        } catch (e) { console.error("加载交易对失败", e); }
    }

    function onConfigChange() {
        const rawInput = document.getElementById('symbol-input').value;
        const interval = document.getElementById('interval-select').value;

        if (rawInput.includes(":")) {
            const parts = rawInput.split(":");
            currentExchange = parts[0];
            currentSymbol = parts[1];
        } else {
            currentSymbol = rawInput;
        }

        series.setData([]); volumeSeries.setData([]);
        legend.innerHTML = `${currentExchange.toUpperCase()}: ${currentSymbol} 加载中...`;

        connectWS();
    }

    window.onConfigChange = onConfigChange;

    function connectWS() {
        const interval = document.getElementById('interval-select').value;

        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ action: "get_history", exchange: currentExchange, symbol: currentSymbol, interval: interval }));
            ws.send(JSON.stringify({ action: "subscribe", symbol: currentSymbol }));
            return;
        }

        ws = new WebSocket(`ws://${window.location.host}/ws`);

        ws.onopen = () => {
            document.getElementById('ws-status').innerText = '🟢 实时同步中';
            document.getElementById('ws-status').className = 'status';

            ws.send(JSON.stringify({ action: "get_history", exchange: currentExchange, symbol: currentSymbol, interval: interval }));
            ws.send(JSON.stringify({ action: "subscribe", symbol: currentSymbol }));

            if(pingInterval) clearInterval(pingInterval);
            pingInterval = setInterval(() => {
                if(ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ action: "ping" }));
            }, 30000);
        };

        ws.onmessage = async (e) => {
            try {
                let textData = e.data;
                if (e.data instanceof Blob) textData = await e.data.text();
                const msg = JSON.parse(textData);
                const currentInterval = document.getElementById('interval-select').value;

                if (msg.type === "history" && msg.data) {
                    const kData = msg.data.map(i => ({ time: i.time - tzOffset, open: i.open, high: i.high, low: i.low, close: i.close }));
                    const vData = msg.data.map(i => ({ time: i.time - tzOffset, value: i.volume, color: i.close >= i.open ? 'rgba(38,166,154,0.5)' : 'rgba(239,83,80,0.5)' }));

                    if (kData.length > 0) {
                        series.setData(kData); volumeSeries.setData(vData);
                        currentBar = kData[kData.length - 1];
                        updateLegend(msg.data[msg.data.length-1], vData[vData.length-1]);
                        if(msg.ticker) {
                            const pct = parseFloat(msg.ticker.priceChangePercent);
                            document.getElementById('ticker-info').innerHTML = `<span style="color:${pct>=0?'#00ff00':'#ff3333'}">${pct>=0?'+':''}${pct.toFixed(2)}%</span>`;
                        }
                    } else {
                        legend.innerHTML = `${currentExchange.toUpperCase()}: ${currentSymbol} 暂无历史数据`;
                    }
                }

                if (msg.type === "realtime" && msg.data && msg.data.symbol === currentSymbol) {
                    const k = msg.data;
                    const snappedTime = snapTime(k.timestamp, currentInterval) - tzOffset;

                    if (!currentBar || snappedTime > currentBar.time) {
                        currentBar = { time: snappedTime, open: k.open, high: k.high, low: k.low, close: k.close };
                        volumeSeries.update({ time: snappedTime, value: k.volume, color: k.close >= k.open ? 'rgba(38,166,154,0.5)' : 'rgba(239,83,80,0.5)' });
                    } else if (snappedTime === currentBar.time) {
                        currentBar.high = Math.max(currentBar.high, k.high);
                        currentBar.low = Math.min(currentBar.low, k.low);
                        currentBar.close = k.close;
                    }
                    series.update(currentBar);
                    updateLegend(k, {value: k.volume});
                }
            } catch (err) { console.error("WS错误:", err); }
        };

        ws.onclose = () => {
            if(pingInterval) clearInterval(pingInterval);
            document.getElementById('ws-status').innerText = '🔴 WS 断开';
            document.getElementById('ws-status').className = 'status offline';
            setTimeout(() => connectWS(currentExchange, currentSymbol, interval), 3000);
        };

        ws.onerror = (err) => {
            console.error('WS 错误:', err);
            document.getElementById('ws-status').innerText = '🔴 WS 连接错误';
            document.getElementById('ws-status').className = 'status offline';
        };
    }

    function updateLegend(k, v) {
        if(!k) return;
        const turnover = k.turnover ? Number(k.turnover).toFixed(2) : '--';
        legend.innerHTML = `${currentExchange.toUpperCase()}: ${currentSymbol} O:${Number(k.open).toFixed(2)} H:${Number(k.high).toFixed(2)} L:${Number(k.low).toFixed(2)} C:${Number(k.close).toFixed(2)} V:${Number(v.value).toFixed(2)} T:${turnover}`;
    }

    document.getElementById('interval-select').addEventListener('change', onConfigChange);
    document.getElementById('symbol-input').addEventListener('change', onConfigChange);
    document.getElementById('symbol-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') onConfigChange(); });

    await loadSymbols();
    connectWS();
});