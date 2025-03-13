# DexScreener Bot

This project is a powerful cryptocurrency trading bot that leverages the [DexScreener API](https://api.dexscreener.com/) to analyze token pairs, detect suspicious activity, and execute trades using Telegram bot commands.

## Features

✅ Tracks token pairs on major chains such as Ethereum, BSC, and Polygon  
✅ Detects suspicious volume patterns (e.g., fake volume)  
✅ Monitors for potential rug pulls and pump-and-dump activities  
✅ Executes buy/sell trades via Telegram commands using the `ToxiSolanaBot`  
✅ Stores token pair data, price history, and analysis results in SQLite  
✅ Flexible configuration for customizing filters, blacklists, and thresholds  

## Requirements
- Python 3.10 or higher
- Telegram Bot Token
- SQLite3 Database
- [DexScreener API](https://api.dexscreener.com/)

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-link>
   cd dexscreener_bot
   ```

2. Install the dependencies:
   ```bash
   pip install requests python-telegram-bot
   ```

3. Create a `config.json` file in the root directory with the following structure:

```json
{
    "filters": {
        "min_liquidity": 1000,
        "min_volume_24h": 10000,
        "min_price_change": -1000
    },
    "blacklisted_coins": [],
    "blacklisted_devs": []
}
```

4. Add your Telegram bot token and chat ID in the `dexscreener_bot.py` file:

```python
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"
```

## Usage

1. Run the bot:
   ```bash
   python dexscreener_bot.py
   ```

2. The bot will:
   - Continuously scan token pairs every 5 minutes.
   - Notify you on Telegram about suspicious activities such as rug pulls, pumps, or fake volume.

## Important Commands

- **Buy**: `/buy <pair_address> <amount> <chain_id>`
- **Sell**: `/sell <pair_address> <amount> <chain_id>`

## Example Output
```
🚨 Fake Volume Detected! 🚨
Token: XYZ
Liquidity: $500
Volume: $100,000
```

## Contributing
Feel free to submit pull requests, report bugs, or suggest features. Your contribution is highly appreciated!

## License
This project is licensed under the MIT License.

CONTACT [LINKEDIN](https://www.linkedin.com/in/umut-kaya-5a9424310/)
