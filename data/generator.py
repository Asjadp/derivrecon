"""
Synthetic Multi-Asset Derivative Trade Feed Generator for DerivRecon
Generates realistic internal OMS trade feeds vs counterparty clearing feeds.
"""
import random
import json
import sys
import os
from datetime import date, timedelta
from typing import List, Tuple, Dict, Any

# Ensure project root is in python path for Linux / Streamlit Cloud deployment
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.models import AssetClass, TradeRecord

COUNTERPARTIES = [
    ("LEI-JPM-001", "JPMorgan Chase Bank NA"),
    ("LEI-GS-002", "Goldman Sachs International"),
    ("LEI-MS-003", "Morgan Stanley & Co LLC"),
    ("LEI-BAML-004", "Bank of America Merrill Lynch"),
    ("LEI-CITI-005", "Citigroup Global Markets"),
    ("LEI-BARC-006", "Barclays Capital Inc"),
]

TRADERS = ["T_ALEXANDER", "T_BECHEL", "T_CHEN", "T_DAVIS", "T_EVANS"]
BOOKS = ["RATES_DESK_NY", "EQUITY_VOL_LDN", "FX_FORWARD_SG", "MACRO_HEDGE_01"]

def generate_trade_batch(count: int = 50, break_ratio: float = 0.30) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    random.seed(42)  # Deterministic seed for reproducible testing & demos
    internal_trades = []
    counterparty_trades = []

    base_date = date(2026, 8, 15)

    for i in range(1, count + 1):
        uti = f"UTI-2026-DERIV-{i:04d}"
        cp_id, cp_name = random.choice(COUNTERPARTIES)
        trader = random.choice(TRADERS)
        book = random.choice(BOOKS)
        trade_dt = (base_date - timedelta(days=random.randint(0, 10))).isoformat()
        settle_dt = (base_date + timedelta(days=random.randint(30, 365))).isoformat()
        
        asset_class_choice = random.choice(list(AssetClass))
        
        # Base trade parameters
        currency = "USD"
        if asset_class_choice == AssetClass.FX_FORWARD:
            currency = random.choice(["EUR/USD", "GBP/USD", "USD/JPY"])

        notional = float(random.choice([1_000_000, 5_000_000, 10_000_000, 25_000_000, 50_000_000]))
        direction = random.choice(["PAY", "RECEIVE"]) if asset_class_choice == AssetClass.INTEREST_RATE_SWAP else random.choice(["BUY", "SELL"])

        # Asset specific details
        details = {}
        if asset_class_choice == AssetClass.INTEREST_RATE_SWAP:
            details = {
                "fixed_rate": round(random.uniform(0.0300, 0.0500), 4),
                "floating_index": random.choice(["SOFR-3M", "EURIBOR-6M"]),
                "payment_frequency": random.choice(["SEMI-ANNUAL", "QUARTERLY"]),
                "day_count_convention": random.choice(["ACT/360", "30/360"])
            }
        elif asset_class_choice == AssetClass.EQUITY_OPTION:
            underlying = random.choice(["SPX", "AAPL", "NVDA", "TSLA"])
            strike = float(random.choice([150, 200, 450, 500, 5500]))
            details = {
                "underlying": underlying,
                "option_type": random.choice(["CALL", "PUT"]),
                "option_style": random.choice(["EUROPEAN", "AMERICAN"]),
                "strike_price": strike,
                "expiration_date": (base_date + timedelta(days=random.randint(15, 180))).isoformat(),
                "premium_amount": round(notional * 0.025, 2)
            }
        elif asset_class_choice == AssetClass.FX_FORWARD:
            spot_rate = round(random.uniform(1.0500, 1.1200), 4)
            forward_points = round(random.uniform(0.0010, 0.0050), 4)
            details = {
                "spot_rate": spot_rate,
                "forward_rate": round(spot_rate + forward_points, 4),
                "dealt_currency": currency.split("/")[0] if "/" in currency else "USD"
            }

        internal_trade = TradeRecord(
            uti=uti,
            trade_date=trade_dt,
            settlement_date=settle_dt,
            counterparty_id=cp_id,
            counterparty_name=cp_name,
            book_id=book,
            trader_id=trader,
            asset_class=asset_class_choice,
            notional=notional,
            currency=currency,
            direction=direction,
            details=details
        ).to_dict()

        # Create counterparty trade (default exact copy)
        cp_trade = json.loads(json.dumps(internal_trade))

        # Inject breaks based on break_ratio
        if random.random() < break_ratio:
            break_scenario = random.choice(["ECONOMIC", "NON_ECONOMIC", "TIMING"])
            
            if break_scenario == "ECONOMIC":
                choice = random.choice(["notional", "rate_or_strike"])
                if choice == "notional":
                    cp_trade["notional"] = notional + random.choice([500_000, 1_000_000, -250_000])
                else:
                    if asset_class_choice == AssetClass.INTEREST_RATE_SWAP:
                        cp_trade["fixed_rate"] = round(cp_trade["fixed_rate"] + 0.0015, 4)
                    elif asset_class_choice == AssetClass.EQUITY_OPTION:
                        cp_trade["strike_price"] = cp_trade["strike_price"] + 10.0
                    elif asset_class_choice == AssetClass.FX_FORWARD:
                        cp_trade["forward_rate"] = round(cp_trade["forward_rate"] + 0.0040, 4)

            elif break_scenario == "NON_ECONOMIC":
                choice = random.choice(["trader_id", "book_id", "cp_name"])
                if choice == "trader_id":
                    cp_trade["trader_id"] = f"{trader}_DESK2"
                elif choice == "book_id":
                    cp_trade["book_id"] = f"{book}_GLOBAL"
                else:
                    cp_trade["counterparty_name"] = cp_name + " (LONDON BRANCH)"

            elif break_scenario == "TIMING":
                # Settlement date shifted by +2 days
                dt_obj = date.fromisoformat(settle_dt)
                cp_trade["settlement_date"] = (dt_obj + timedelta(days=2)).isoformat()

        internal_trades.append(internal_trade)
        counterparty_trades.append(cp_trade)

    # Add 2 unmatched internal trades and 2 unmatched counterparty trades for realistic orphan trade breaks
    unmatched_int_uti = f"UTI-2026-DERIV-{count+1:04d}"
    unmatched_cp_uti = f"UTI-2026-DERIV-{count+2:04d}"

    orphan_int = TradeRecord(
        uti=unmatched_int_uti,
        trade_date=base_date.isoformat(),
        settlement_date=(base_date + timedelta(days=90)).isoformat(),
        counterparty_id="LEI-JPM-001",
        counterparty_name="JPMorgan Chase Bank NA",
        book_id="RATES_DESK_NY",
        trader_id="T_ALEXANDER",
        asset_class=AssetClass.INTEREST_RATE_SWAP,
        notional=15_000_000.0,
        currency="USD",
        direction="PAY",
        details={"fixed_rate": 0.0410, "floating_index": "SOFR-3M", "payment_frequency": "QUARTERLY", "day_count_convention": "ACT/360"}
    ).to_dict()

    orphan_cp = TradeRecord(
        uti=unmatched_cp_uti,
        trade_date=base_date.isoformat(),
        settlement_date=(base_date + timedelta(days=60)).isoformat(),
        counterparty_id="LEI-GS-002",
        counterparty_name="Goldman Sachs International",
        book_id="EQUITY_VOL_LDN",
        trader_id="T_CHEN",
        asset_class=AssetClass.EQUITY_OPTION,
        notional=8_000_000.0,
        currency="USD",
        direction="BUY",
        details={"underlying": "SPX", "option_type": "CALL", "option_style": "EUROPEAN", "strike_price": 5400.0, "expiration_date": (base_date + timedelta(days=60)).isoformat(), "premium_amount": 200000.0}
    ).to_dict()

    internal_trades.append(orphan_int)
    counterparty_trades.append(orphan_cp)

    return internal_trades, counterparty_trades

def save_feeds_to_file(internal_path: str = "data/internal_trades.json", cp_path: str = "data/counterparty_trades.json", count: int = 50):
    internal, cp = generate_trade_batch(count=count)
    with open(internal_path, "w") as f:
        json.dump(internal, f, indent=2)
    with open(cp_path, "w") as f:
        json.dump(cp, f, indent=2)
    print(f"Generated {len(internal)} internal trades and {len(cp)} counterparty trades.")

if __name__ == "__main__":
    save_feeds_to_file()
