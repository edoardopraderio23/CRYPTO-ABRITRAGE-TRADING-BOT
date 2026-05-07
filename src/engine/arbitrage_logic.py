"""
PARTNER B (Edoardo): Quant Strategy & Math Engine
Task: Implement Triangular Arbitrage logic using a 3-step cycle.
Date: 04/30/2026
"""


class ArbitrageEngine:
    """Triangular-arbitrage profitability calculator (v0.1 stub).

    Computes the post-fee return of a USDT → BTC → ETH → USDT cycle
    given three observed market rates. This is a pure math primitive;
    it does not yet wrap the Profit Gate or the graph-based Brain
    described in TECHNICAL_PLAN.md — those come in v0.2.
    """

    def __init__(self, fee_percent: float = 0.001) -> None:
        # Default exchange taker fee is 0.10% per leg
        self.fee = fee_percent

    def calculate_triangular_profit(
        self,
        btc_usdt: float,
        eth_btc: float,
        eth_usdt: float,
        starting_usdt: float = 1.0,
    ) -> dict:
        """Simulate a 1-USDT round trip USDT → BTC → ETH → USDT.

        Returns a dict with starting_usdt, final_usdt, profit, profit_pct.
        Fee is applied multiplicatively on each leg.
        """
        keep = 1.0 - self.fee

        # Leg 1: USDT -> BTC
        btc_amount = (starting_usdt / btc_usdt) * keep
        # Leg 2: BTC -> ETH  (sell BTC, buy ETH at price eth_btc BTC per ETH)
        eth_amount = (btc_amount / eth_btc) * keep
        # Leg 3: ETH -> USDT
        final_usdt = (eth_amount * eth_usdt) * keep

        profit = final_usdt - starting_usdt
        return {
            "starting_usdt": starting_usdt,
            "final_usdt": final_usdt,
            "profit": profit,
            "profit_pct": (profit / starting_usdt) * 100.0,
        }


if __name__ == "__main__":
    engine = ArbitrageEngine()
    # Simulated prices: BTC/USDT=60000, ETH/BTC=0.0520, ETH/USDT=3150
    results = engine.calculate_triangular_profit(60000.00, 0.0520, 3150.00)
    print(results)
