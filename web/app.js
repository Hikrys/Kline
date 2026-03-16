document.addEventListener('DOMContentLoaded', async function() {
    if (typeof LightweightCharts === 'undefined') {
        alert('图表库加载失败，请刷新页面重试！');
        document.getElementById('legend').innerText = '❌ 图表库加载失败';
        return;
    }

    const chart = LightweightCharts.createChart(document.getElementById('chart-container'), {
        layout: { textColor: '#d1d4dc', background: { type: 'solid', color: '#131722' } },
        grid: { vertLines: { color: '#363c4e' }, horzLines: { color: '#363c4e' } },
        crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
        timeScale: { timeVisible: true, secondsVisible: false }
    });

    chart.priceScale('right').applyOptions({
        scaleMargins: { top: 0.1, bottom: 0.25 }
    });

    chart.priceScale('').applyOptions({
        scaleMargins: { top: 0.8, bottom: 0 }
    });

    const series = chart.addCandlestickSeries({ upColor: '#26a69a', downColor: '#ef5350', borderVisible: false, wickUpColor: '#26a69a', wickDownColor: '#ef5350' });

    //  priceScaleId: '' 必须配合上面的 chart.priceScale('') 才能防止挤压！
    const volumeSeries = chart.addHistogramSeries({ color: '#26a69a', priceFormat: { type: 'volume' }, priceScaleId: '' });

    const legend = document.getElementById('legend');
    const tzOffset = new Date().getTimezoneOffset() * 60;

    let ws = null;
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

        if(ws && ws.readyState === WebSocket.OPEN) ws.close();
        connectWS(currentExchange, currentSymbol, interval);
    }

    window.onConfigChange = onConfigChange;

    function connectWS(exchange, symbol, interval) {
        ws = new WebSocket(`ws://${window.location.host}/ws`);

        ws.onopen = () => {
            document.getElementById('ws-status').innerText = '🟢 实时同步中';
            document.getElementById('ws-status').className = 'status';

            ws.send(JSON.stringify({ action: "get_history", exchange: exchange, symbol: symbol, interval: interval }));
            ws.send(JSON.stringify({ action: "subscribe", symbol: symbol }));

            setInterval(() => {
                if(ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({ action: "ping" }));
                }
            }, 30000);
        };

        ws.onmessage = async (e) => {
            try {
                let textData = e.data;
                if (e.data instanceof Blob) {
                    textData = await e.data.text();
                }
                const msg = JSON.parse(textData);

                if (msg.type === "history" && msg.data) {
                    const kData = msg.data.map(i => ({ time: i.time - tzOffset, open: i.open, high: i.high, low: i.low, close: i.close }));
                    const vData = msg.data.map(i => ({ time: i.time - tzOffset, value: i.volume, color: i.close >= i.open ? 'rgba(38,166,154,0.5)' : 'rgba(239,83,80,0.5)' }));

                    if (kData.length > 0) {
                        series.setData(kData); volumeSeries.setData(vData);

                        updateLegend(msg.data[msg.data.length-1], vData[vData.length-1]);

                        if(msg.ticker) {
                            const pct = parseFloat(msg.ticker.priceChangePercent);
                            const color = pct >= 0 ? '#00ff00' : '#ff3333';
                            const sign = pct >= 0 ? '+' : '';
                            document.getElementById('ticker-info').innerHTML =
                                `<span style="color:${color}">${sign}${pct.toFixed(2)}%</span>`;
                        }
                    } else {
                        legend.innerHTML = `⚠️ ${exchange.toUpperCase()}: ${symbol} ${interval} 暂无历史数据`;
                    }
                }

                if (msg.type === "realtime" && msg.data && msg.data.symbol === currentSymbol) {
                    const k = msg.data;
                    const timeStr = Math.floor(k.timestamp / 1000) - tzOffset;
                    series.update({ time: timeStr, open: k.open, high: k.high, low: k.low, close: k.close });
                    volumeSeries.update({ time: timeStr, value: k.volume, color: k.close >= k.open ? 'rgba(38,166,154,0.5)' : 'rgba(239,83,80,0.5)' });

                    updateLegend(k, {value: k.volume});
                }
            } catch (err) {
                console.error("解析 WebSocket 数据失败:", err);
            }
        };

        ws.onclose = () => {
            document.getElementById('ws-status').innerText = '🔴 WS 断开';
            document.getElementById('ws-status').className = 'status offline';
            setTimeout(() => connectWS(exchange, symbol, interval), 3000);
        };
    }

    function updateLegend(k, v) {
        if(!k) return;
        const open = Number(k.open).toFixed(2);
        const high = Number(k.high).toFixed(2);
        const low = Number(k.low).toFixed(2);
        const close = Number(k.close).toFixed(2);
        const volume = Number(v.value).toFixed(2);

        const turnover = k.turnover ? Number(k.turnover).toFixed(2) : '--';
        legend.innerHTML = `${currentExchange.toUpperCase()}: ${currentSymbol} O:${open} H:${high} L:${low} C:${close} V:${volume} T:${turnover}`;
    }

    document.getElementById('symbol-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') onConfigChange();
    });

    await loadSymbols();
    connectWS(currentExchange, currentSymbol, "1m");
});