# BingX BTC-USDT Perpetual Futures Trading Bot v2 (Modern Full-Stack)

Bu repo, BingX borsası ile entegre çalışan, Neon PostgreSQL veritabanı destekli, modern bir BTC-USDT Perpetual Futures trading terminalidir.

## Özellikler

- **Modern Terminal (FastAPI + Vue.js)**: Kurumsal düzeyde "Vertex Terminal" arayüzü.
- **Canlı Analitik**: Win-rate, Ortalama Kar, Best/Worst trade takibi.
- **Kalıcı Geçmiş (Neon PostgreSQL)**: Tüm işlemler ve bakiye geçmişi veritabanında saklanır.
- **Kümülatif PNL Grafiği**: Performansınızı zaman içinde ApexCharts ile görselleştirin.
- **Gelişmiş TradingView Grafiği**: RSI ve EMA indikatörlü candlestick chart.
- **Streamlit Dashboard (Yedek)**: Alternatif olarak `app.py` üzerinden Streamlit arayüzü kullanılabilir.
- **Otomatik Strateji**: 1 saatlik timeframe'de RSI ve 50-periyotluk EMA tabanlı sinyaller.
- **Risk Yönetimi**: %30 sabit stop-loss ve 1:2 Risk-Ödül oranlı otomatik take-profit.

## Kurulum & Çalıştırma

1. Gerekli kütüphaneleri yükleyin:
   ```bash
   pip install -r requirements.txt
   ```
2. `.env` dosyanızı oluşturun:
   ```env
   BINGX_API_KEY=your_key
   BINGX_API_SECRET=your_secret
   DATABASE_URL=postgresql://user:pass@host/neondb?sslmode=require
   ```
3. Uygulamayı başlatın:
   ```bash
   python backend.py
   ```
4. Tarayıcınızdan `http://localhost:8000` adresine gidin.

## Dosya Yapısı

- `backend.py`: FastAPI backend ve Neon veritabanı entegrasyonu.
- `index.html`: Vue.js ve Tailwind CSS tabanlı modern frontend.
- `bot.py`: BingXBot motoru ve ticaret mantığı.
- `app.py`: Streamlit dashboard (Opsiyonel).
- `utils.py` & `backtest.py`: Yardımcı araçlar ve strateji test motoru.

## Deployment

Proje Render üzerinde yayına hazırdır. `DATABASE_URL` env variable'ı Neon connection string ile ayarlanmalıdır.

---
**Uyarı:** Bu yazılım finansal tavsiye niteliği taşımaz. Gerçek para ile işlem yapmadan önce mutlaka Sandbox modunda test edin.
