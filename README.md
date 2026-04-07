# BingX BTC-USDT Perpetual Futures Trading Bot

Bu repo, Python ve Streamlit kullanılarak geliştirilmiş, BingX borsası ile entegre çalışan bir BTC-USDT Perpetual Futures trading botudur.

## Özellikler

- **Canlı Dashboard**: Streamlit tabanlı kullanıcı dostu arayüz.
- **Gerçek Zamanlı Veri**: BTC-USDT fiyatı ve 24 saatlik değişim takibi.
- **İndikatörler**: RSI ve EMA (50) overlay'li canlı grafik.
- **Otomatik Strateji**:
  - LONG: RSI < 35 & Fiyat > 50 EMA.
  - SHORT: RSI > 65 & Fiyat < 50 EMA.
- **Risk Yönetimi**:
  - %30 Sabit Stop-Loss (Kaldıraç dahil pozisyon bazlı).
  - Otomatik Take-Profit (1:2 RR veya RSI ters sinyali).
- **Esneklik**: Manuel Long/Short açma ve pozisyon kapatma butonları.
- **Backtest**: Geçmiş veriler üzerinde strateji simülasyonu.
- **Modlar**: Sandbox (Demo) ve Real mode desteği.

## Kurulum

1. Depoyu klonlayın.
2. Gerekli kütüphaneleri yükleyin:
   ```bash
   pip install -r requirements.txt
   ```
3. `.env.example` dosyasını `.env` olarak kopyalayın ve API anahtarlarınızı girin.
4. Uygulamayı başlatın:
   ```bash
   streamlit run app.py
   ```

## Dosya Yapısı

- `app.py`: Streamlit UI ve ana uygulama döngüsü.
- `bot.py`: BingXBot sınıfı, borsa entegrasyonu ve ticaret mantığı.
- `utils.py`: İndikatör hesaplamaları ve yardımcı fonksiyonlar.
- `backtest.py`: Geçmiş veri analiz motoru.

## Uyarı
Bu bir eğitim projesidir. Gerçek para ile ticaret yapmadan önce Sandbox modunda iyice test edin.
