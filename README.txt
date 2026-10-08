POCKET SCREENER  -  NASDAQ + NYSE + Binance, three rules
Result must pass ALL of: P/E < 20, volume > 2x its 20-day average, RSI(14) > 50.
Crypto has no P/E, so Binance coins are held to the volume and RSI rules only.

HOW IT WORKS
- Crypto: the app scans Binance USDT pairs live from your phone each time you open it or tap Scan now.
- Stocks: build_data.py scans NASDAQ and NYSE common stocks and writes data.json. The app reads that file.

SET UP ONCE (about 10 minutes, free)
1. Create a GitHub repo and upload everything in this folder, including the hidden .github folder.
2. Repo Settings > Pages > deploy from branch main, root folder. Note the https link it gives you.
3. Repo Actions tab > "Refresh stock scan" > Run workflow. It takes 10 to 25 minutes the first time.
   After that it runs by itself every weekday at 22:15 UTC, after the US close.
4. Open the Pages link on your phone.
   iPhone (Safari): Share > Add to Home Screen.   Android (Chrome): menu > Install app.

NOTES
- Binance blocks some countries. If the Binance line shows an error, try another network.
- P/E is trailing twelve months. Companies with negative earnings have no usable P/E and are dropped.
- NYSE means exchange N only. Edit INCLUDE_EXCHANGES in build_data.py to add NYSE American or Arca.
- Stock data comes from Yahoo Finance through the yfinance library. It is unofficial and can change or rate-limit.
- To run it on your own computer instead: pip install -r requirements.txt, then python build_data.py.
