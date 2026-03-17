document.addEventListener('DOMContentLoaded', async function() {
    if (typeof LightweightCharts === 'undefined') {
        alert('图表库加载失败，请刷新页面重试！');
        return;
    }

    const chart = LightweightCharts.createChart(document.getElementById('chart-container'), {
        layout: { textColor: '#d1d4dc', background: { type: 'solid', color: '#131722' } },
        grid: { vertLines: { color: '#363c4e' }, horzLines: { color: '#363c4e' } },
        crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
        timeScale: { timeVisible: true, secondsVisible: false }
    });

    chart.priceScale('right').applyOptions({ scaleMargins: { top: 0.1, bottom: 0.25 } });
    chart.priceScale('').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

    const series = chart.addCandlestickSeries({ upColor: '#26a69a', downColor: '#ef5350', borderVisible: false, wickUpColor: '#26a69a', wickDownColor: '#ef5350' });
    const volumeSeries = chart.addHistogramSeries({ color: '#26a69a', priceFormat: { type: 'volume' }, priceScaleId: '' });

    const legend = document.getElementById('legend');
    const tzOffset = new Date().getTimezoneOffset() * 60;

    let ws = null;
    let pingInterval = null; // 记录心跳定时器，防止泄漏
    let currentExchange = "binance";
    let currentSymbol = "BTC/USDT";

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
        if (rawInput.includes(":")) {
            const parts = rawInput.split(":");
            currentExchange = parts[0];
            currentSymbol = parts[1];
        } else {
            currentSymbol = rawInput;
        }

        series.setData([]); volumeSeries.setData([]);
        legend.innerHTML = `${currentExchange.toUpperCase()}: ${currentSymbol} 加载中...`;

        // 💡【核心修复1】：不再暴力断开 WS！复用同一条连接，只发送新指令！
        connectWS();
    }
    window.onConfigChange = onConfigChange;

    function connectWS() {
        const interval = document.getElementById('interval-select').value;

        // 如果连接已存在且正常，直接发送新指令，直接 return！
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

            // 💡【核心修复2】：建立新连接时，先清理旧的定时器，防止泄漏！
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
                        updateLegend(msg.data[msg.data.length-1], vData[vData.length-1]);
                        if(msg.ticker) {
                            const pct = parseFloat(msg.ticker.priceChangePercent);
                            document.getElementById('ticker-info').innerHTML = `<span style="color:${pct>=0?'#00ff00':'#ff3333'}">${pct>=0?'+':''}${pct.toFixed(2)}%</span>`;
                        }
                    } else {
                        legend.innerHTML = `⚠️ ${currentExchange.toUpperCase()}: ${currentSymbol} 暂无历史数据`;
                    }
                }

                if (msg.type === "realtime" && msg.data && msg.data.symbol === currentSymbol) {
                    const k = msg.data;
                    // 把后端传来的 1m 实时数据的时间戳，向下取整对齐到当前前端选择的周期！
                    const intervalSecs = { '1m': 60, '5m': 300, '15m': 900, '1h': 3600, '4h': 14400, '1d': 86400 }[currentInterval] || 60;
                    // 对齐算法：去除余数，吸附到整点/整小时
                    const flooredTime = Math.floor(k.timestamp / 1000 / intervalSecs) * intervalSecs - tzOffset;

                    series.update({ time: flooredTime, open: k.open, high: k.high, low: k.low, close: k.close });
                    volumeSeries.update({ time: flooredTime, value: k.volume, color: k.close >= k.open ? 'rgba(38,166,154,0.5)' : 'rgba(239,83,80,0.5)' });
                    updateLegend(k, {value: k.volume});
                }
            } catch (err) { console.error("解析 WS 失败:", err); }
        };

        ws.onclose = () => {
            if(pingInterval) clearInterval(pingInterval);
            document.getElementById('ws-status').innerText = '🔴 WS 断开';
            document.getElementById('ws-status').className = 'status offline';
            setTimeout(connectWS, 3000);
        };
    }

    function updateLegend(k, v) {
        if(!k) return;
        const turnover = k.turnover ? Number(k.turnover).toFixed(2) : '--';
        legend.innerHTML = `${currentExchange.toUpperCase()}: ${currentSymbol} O:${Number(k.open).toFixed(2)} H:${Number(k.high).toFixed(2)} L:${Number(k.low).toFixed(2)} C:${Number(k.close).toFixed(2)} V:${Number(v.value).toFixed(2)} T:${turnover}`;
    }

    document.getElementById('symbol-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') onConfigChange(); });

    await loadSymbols();
    connectWS();
});