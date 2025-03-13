import requests
import time
import sqlite3
from datetime import datetime, timedelta
import json
import logging
from typing import Dict, List, Optional, Set
from telegram import Bot
import asyncio

# Configure logging
logging.basicConfig(
    filename='dexscreener_bot.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Constants
API_BASE_URL = "https://api.dexscreener.com/latest/dex/pairs"
CHAINS = ["ethereum", "bsc", "polygon"]
REQUEST_DELAY = 0.2
DB_NAME = "token_analysis.db"
CONFIG_FILE = "config.json"
POCKET_UNIVERSE_API = "https://api.pocketuniverse.app/v1/check_volume"  # Hypothetical
RUGCHECK_URL = "https://rugcheck.xyz"  # Base URL
TOXISOL_TG_BOT = "ToxiSolanaBot"  # Replace with actual handle if different
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"  # Replace with your bot token
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"  # Replace with your chat ID

# Default thresholds
RUG_THRESHOLD = -50
PUMP_THRESHOLD = 100
NEW_PAIR_HOURS = 24

class FilterConfig:
    def __init__(self, min_liquidity: float = 1000, min_volume_24h: float = 10000, min_price_change: float = -1000):
        self.min_liquidity = min_liquidity
        self.min_volume_24h = min_volume_24h
        self.min_price_change = min_price_change

    def passes(self, liquidity: float, volume_24h: float, price_change: float) -> bool:
        return (liquidity >= self.min_liquidity and 
                volume_24h >= self.min_volume_24h and 
                price_change >= self.min_price_change)

class DexScreenerBot:
    def __init__(self):
        self.conn = sqlite3.connect(DB_NAME)
        self.cursor = self.conn.cursor()
        self._setup_database()
        self.filters, self.blacklisted_coins, self.blacklisted_devs = self._load_config()
        self.session = requests.Session()
        self.tg_bot = Bot(TELEGRAM_TOKEN)
        logging.info("DexScreenerBot initialized with ToxiSol integration.")

    def _load_config(self) -> tuple[FilterConfig, Set[str], Set[str]]:
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
            filters = FilterConfig(
                min_liquidity=config.get("filters", {}).get("min_liquidity", 1000),
                min_volume_24h=config.get("filters", {}).get("min_volume_24h", 10000),
                min_price_change=config.get("filters", {}).get("min_price_change", -1000)
            )
            blacklisted_coins = set(config.get("blacklisted_coins", []))
            blacklisted_devs = set(config.get("blacklisted_devs", []))
            return filters, blacklisted_coins, blacklisted_devs
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logging.warning(f"Config load failed: {e}. Using defaults.")
            return FilterConfig(), set(), set()

    def _setup_database(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS token_pairs (
                pair_address TEXT PRIMARY KEY,
                chain_id TEXT,
                base_token TEXT,
                quote_token TEXT,
                created_at INTEGER,
                first_seen TIMESTAMP,
                dev_wallet TEXT
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pair_address TEXT,
                price_usd REAL,
                volume_24h REAL,
                liquidity_usd REAL,
                price_change_24h REAL,
                timestamp TIMESTAMP,
                FOREIGN KEY (pair_address) REFERENCES token_pairs (pair_address)
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS analysis (
                pair_address TEXT,
                event_type TEXT,
                detected_at TIMESTAMP,
                details TEXT,
                FOREIGN KEY (pair_address) REFERENCES token_pairs (pair_address)
            )
        ''')
        self.conn.commit()

    def fetch_pair_data(self, chain: str, pair_address: Optional[str] = None) -> Dict:
        url = f"{API_BASE_URL}/{chain}" if not pair_address else f"{API_BASE_URL}/{chain}/{pair_address}"
        try:
            response = self.session.get(url)
            response.raise_for_status()
            data = response.json()
            return data.get("pairs", [data.get("pair", {})])[0] if pair_address else data.get("pairs", [])
        except requests.RequestException as e:
            logging.error(f"Failed to fetch data for {chain}/{pair_address}: {e}")
            return {}

    def check_fake_volume(self, pair: Dict) -> bool:
        pair_address = pair.get("pairAddress")
        chain_id = pair.get("chainId")
        volume_24h = float(pair.get("volume", {}).get("h24", 0))
        liquidity_usd = float(pair.get("liquidity", {}).get("usd", 0))
        payload = {"chain": chain_id, "pair_address": pair_address, "volume_24h": volume_24h, "liquidity_usd": liquidity_usd}
        try:
            response = self.session.post(POCKET_UNIVERSE_API, json=payload, timeout=5)
            response.raise_for_status()
            result = response.json()
            is_fake = result.get("is_fake_volume", False)
            if is_fake:
                logging.info(f"Fake volume detected for {pair_address}: {result.get('reason', 'No reason')}")
            return is_fake
        except requests.RequestException as e:
            logging.error(f"Pocket Universe API error for {pair_address}: {e}")
            return False

    def update_blacklist(self, pair: Dict):
        pair_address = pair.get("pairAddress")
        base_token = pair["baseToken"]["symbol"]
        if self.check_fake_volume(pair):
            self.blacklisted_coins.add(pair_address)
            self.blacklisted_coins.add(base_token)
            with open(CONFIG_FILE, 'r+') as f:
                config = json.load(f)
                config["blacklisted_coins"] = list(self.blacklisted_coins)
                f.seek(0)
                json.dump(config, f, indent=4)
                f.truncate()
            logging.info(f"Added {pair_address} ({base_token}) to blacklist due to fake volume.")

    def check_rugcheck_rating(self, pair_address: str) -> bool:
        try:
            url = f"{RUGCHECK_URL}/api/check"  # Hypothetical
            params = {"token_address": pair_address}
            response = self.session.get(url, params=params, timeout=5)
            response.raise_for_status()
            result = response.json()
            rating = result.get("rating", "").lower()
            is_good = rating == "good"
            logging.info(f"RugCheck rating for {pair_address}: {rating}")
            return is_good
        except requests.RequestException as e:
            logging.error(f"RugCheck check failed for {pair_address}: {e}")
            return False

    async def send_telegram_notification(self, message: str):
        try:
            await self.tg_bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
            logging.info(f"Sent Telegram notification: {message}")
        except Exception as e:
            logging.error(f"Failed to send Telegram notification: {e}")

    def execute_toxisol_trade(self, pair: Dict, action: str, amount: float) -> bool:
        pair_address = pair.get("pairAddress")
        base_token = pair["baseToken"]["symbol"]
        chain_id = pair["chainId"]
        command = f"/{action} {pair_address} {amount} {chain_id}"
        try:
            asyncio.run(self.send_telegram_notification(f"@{TOXISOL_TG_BOT} {command}"))
            logging.info(f"Executed {action} trade for {pair_address} via ToxiSol: {amount}")
            notification = f"{action.upper()} executed for {base_token} ({pair_address}): {amount} units"
            asyncio.run(self.send_telegram_notification(notification))
            return True
        except Exception as e:
            logging.error(f"ToxiSol trade failed for {pair_address}: {e}")
            return False

    def analyze_pair(self, pair: Dict) -> None:
        pair_address = pair.get("pairAddress")
        if not pair_address:
            return

        base_token = pair["baseToken"]["symbol"]
        quote_token = pair["quoteToken"]["symbol"]
        dev_wallet = pair.get("pairCreatedBy", "unknown")

        if not self.check_rugcheck_rating(pair_address):
            logging.info(f"Pair {pair_address} not rated 'Good' by RugCheck. Skipping.")
            return

        self.update_blacklist(pair)
        if (base_token in self.blacklisted_coins or quote_token in self.blacklisted_coins or
            pair_address in self.blacklisted_coins or dev_wallet in self.blacklisted_devs):
            logging.info(f"Pair {pair_address} blacklisted (coin: {base_token}/{quote_token}, dev: {dev_wallet})")
            return

        self.cursor.execute("SELECT first_seen FROM token_pairs WHERE pair_address = ?", (pair_address,))
        if not self.cursor.fetchone():
            self._save_new_pair(pair, dev_wallet)

        price_usd = float(pair.get("priceUsd", 0))
        volume_24h = float(pair.get("volume", {}).get("h24", 0))
        liquidity_usd = float(pair.get("liquidity", {}).get("usd", 0))
        price_change_24h = float(pair.get("priceChange", {}).get("h24", 0))
        timestamp = datetime.utcnow()

        if not self.filters.passes(liquidity_usd, volume_24h, price_change_24h):
            logging.debug(f"Pair {pair_address} filtered out: liquidity={liquidity_usd}, volume={volume_24h}, change={price_change_24h}")
            return

        self.cursor.execute("""
            INSERT INTO price_history (pair_address, price_usd, volume_24h, liquidity_usd, price_change_24h, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (pair_address, price_usd, volume_24h, liquidity_usd, price_change_24h, timestamp))

        if price_change_24h < RUG_THRESHOLD and liquidity_usd < 1000:
            self._detect_rug_pull(pair_address, price_change_24h, liquidity_usd, timestamp)
        elif price_change_24h > PUMP_THRESHOLD and volume_24h > 100000:
            self._detect_pump(pair_address, price_change_24h, volume_24h, timestamp)
            self.execute_toxisol_trade(pair, "buy", 1.0)  # Buy on pump
        elif price_change_24h < -10:
            self.execute_toxisol_trade(pair, "sell", 0.5)  # Sell on dip

        self.conn.commit()

    def _save_new_pair(self, pair: Dict, dev_wallet: str) -> None:
        pair_address = pair["pairAddress"]
        chain_id = pair["chainId"]
        base_token = pair["baseToken"]["symbol"]
        quote_token = pair["quoteToken"]["symbol"]
        created_at = pair.get("pairCreatedAt", 0) // 1000
        first_seen = datetime.utcnow()

        self.cursor.execute("""
            INSERT OR IGNORE INTO token_pairs (pair_address, chain_id, base_token, quote_token, created_at, first_seen, dev_wallet)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (pair_address, chain_id, base_token, quote_token, created_at, first_seen, dev_wallet))

        if (datetime.utcnow() - datetime.fromtimestamp(created_at)) < timedelta(hours=NEW_PAIR_HOURS):
            self.cursor.execute("""
                INSERT INTO analysis (pair_address, event_type, detected_at, details)
                VALUES (?, ?, ?, ?)
            """, (pair_address, "new", first_seen, json.dumps({"age_hours": NEW_PAIR_HOURS})))
            logging.info(f"New pair detected: {pair_address}")

    def _detect_rug_pull(self, pair_address: str, price_change: float, liquidity: float, timestamp: datetime) -> None:
        if price_change < RUG_THRESHOLD and liquidity < 1000:
            details = {"price_change_24h": price_change, "liquidity_usd": liquidity}
            self.cursor.execute("""
                INSERT INTO analysis (pair_address, event_type, detected_at, details)
                VALUES (?, ?, ?, ?)
            """, (pair_address, "rug", timestamp, json.dumps(details)))
            logging.info(f"Rug pull detected: {pair_address}")

    def _detect_pump(self, pair_address: str, price_change: float, volume: float, timestamp: datetime) -> None:
        if price_change > PUMP_THRESHOLD and volume > 100000:
            details = {"price_change_24h": price_change, "volume_24h": volume}
            self.cursor.execute("""
                INSERT INTO analysis (pair_address, event_type, detected_at, details)
                VALUES (?, ?, ?, ?)
            """, (pair_address, "pump", timestamp, json.dumps(details)))
            logging.info(f"Pump detected: {pair_address}")

    def run(self):
        while True:
            for chain in CHAINS:
                pairs = self.fetch_pair_data(chain)
                if isinstance(pairs, list):
                    for pair in pairs:
                        self.analyze_pair(pair)
                        time.sleep(REQUEST_DELAY)
                else:
                    self.analyze_pair(pairs)
                    time.sleep(REQUEST_DELAY)
            logging.info(f"Completed scan of {CHAINS}. Sleeping for 5 minutes.")
            time.sleep(300)

if __name__ == "__main__":
    bot = DexScreenerBot()
    bot.run()