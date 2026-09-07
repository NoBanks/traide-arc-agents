"""
agents.py - the three strategies.

All three share one rule that is not negotiable and is enforced in decide():
if The Graph gave us no usable live signal this cycle, the agent returns HOLD
with the refusal reason. There is no other data source in this package. The
DexScreener pricing used by the pre-existing paper agent (clip_sim.py in the
TRAIDE agent backend) is deliberately absent here; it is not imported, not
called, and not available as a fallback.

  PASSIVE     trades only on a clear signal and always the smallest size.
              Contrarian: buys LINK when the market is quiet or the reference
              price is falling, sells into strength.
  AGGRESSIVE  trend follower. Buys LINK when activity or price is rising, sells
              when falling, and scales size with the strength of the signal.
  REBALANCE   holds a target 50/50 split of its own inventory by pool value and
              trades the difference back toward target. It REQUIRES the price
              tier, because a value split is meaningless without a reference
              price, so it stays flat until GRAPH_API_KEY is set. That is the
              load-bearing rule made visible: one agent that literally cannot
              act without The Graph's authenticated data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from . import config
from .graph import GraphSignal, NO_KEY_MESSAGE

Action = Literal["BUY_LINK", "SELL_LINK", "HOLD"]

# Thresholds. Chosen so a flat market produces HOLD rather than churn.
ACTIVITY_STRONG = 0.15
ACTIVITY_WEAK = 0.04
PRICE_MOVE = 0.002  # 0.2 percent over the OHLC window
REBALANCE_BAND = 0.08  # act when the split is more than 8 points off target


@dataclass
class Decision:
    action: Action
    reason: str
    size_usdc_units: int = 0
    size_link_wei: int = 0

    @property
    def trades(self) -> bool:
        return self.action != "HOLD"


def _clamp_usdc(units: int) -> int:
    return max(config.SWAP_MIN_USDC_UNITS, min(int(units), config.SWAP_MAX_USDC_UNITS))


def _hold(reason: str) -> Decision:
    return Decision(action="HOLD", reason=reason)


def decide(
    agent: str,
    signal: GraphSignal,
    balances: dict[str, int],
    reserves: dict[str, int],
) -> Decision:
    """
    Turn a live Graph signal plus on-chain state into one decision.

    balances: the agent's own usdc_units_6 and link_wei_18.
    reserves: the TRAIDEAMM pair's usdc_units_6 and link_wei_18.
    """
    # ---- the load-bearing guard. Nothing below runs without a live Graph signal.
    if not signal.usable:
        if not any("no API key" in n for n in signal.notes):
            return _hold("[GRAPH] no live signal this cycle, not trading")
        return _hold(NO_KEY_MESSAGE)

    usdc = balances.get("usdc_units_6", 0)
    link = balances.get("link_wei_18", 0)
    activity = signal.activity_score
    change = signal.price_change

    # Never spend the whole gas balance. Arc gas is the same asset we trade.
    spendable_usdc = max(usdc - 200_000, 0)  # keep 0.2 USDC for gas

    if agent == "REBALANCE":
        if not signal.has_price:
            return _hold(
                "REBALANCE requires the authenticated Graph price tier; "
                + (NO_KEY_MESSAGE if not signal.price else "price tier unavailable")
            )
        return _rebalance(usdc, link, spendable_usdc, reserves, change or 0.0)

    if agent == "AGGRESSIVE":
        return _aggressive(spendable_usdc, link, activity, change)

    if agent == "PASSIVE":
        return _passive(spendable_usdc, link, activity, change)

    return _hold(f"unknown agent {agent}")


def _direction(activity: float | None, change: float | None) -> tuple[int, str]:
    """
    Combine the two Graph tiers into one direction. Price, when present, leads;
    activity confirms or, alone, decides. Returns (-1, 0, 1) and the reason.
    """
    if change is not None:
        if change > PRICE_MOVE:
            return 1, f"Graph price tier: reference close up {change * 100:.2f} percent"
        if change < -PRICE_MOVE:
            return -1, f"Graph price tier: reference close down {abs(change) * 100:.2f} percent"
    if activity is not None:
        if activity > ACTIVITY_STRONG:
            return 1, f"Graph activity tier: DEX momentum {activity:.3f} above {ACTIVITY_STRONG}"
        if activity < -ACTIVITY_WEAK:
            return -1, f"Graph activity tier: DEX momentum {activity:.3f} below {-ACTIVITY_WEAK}"
        return 0, f"Graph activity tier: DEX momentum {activity:.3f} inside the dead band"
    return 0, "Graph signal present but carried no directional value"


def _aggressive(spendable_usdc: int, link: int, activity: float | None, change: float | None) -> Decision:
    direction, reason = _direction(activity, change)
    if direction == 0:
        return _hold("AGGRESSIVE stands down. " + reason)

    strength = abs(change) * 50 if change is not None else abs(activity or 0.0)
    scale = min(max(strength, 0.2), 1.0)
    size = _clamp_usdc(
        config.SWAP_MIN_USDC_UNITS
        + int((config.SWAP_MAX_USDC_UNITS - config.SWAP_MIN_USDC_UNITS) * scale)
    )

    if direction > 0:
        if spendable_usdc < size:
            return _hold(f"AGGRESSIVE would buy but holds only {spendable_usdc} USDC units spendable")
        return Decision("BUY_LINK", "AGGRESSIVE follows the trend. " + reason, size_usdc_units=size)

    # Sell an amount of LINK worth roughly the same USDC size, using the pool rate
    # at call time in the runner. Here we express it as a fraction of inventory.
    if link <= 0:
        return _hold("AGGRESSIVE would sell but holds no LINK")
    portion = int(link * scale * 0.1)
    if portion <= 0:
        return _hold("AGGRESSIVE sell size rounded to zero")
    return Decision("SELL_LINK", "AGGRESSIVE follows the trend. " + reason, size_link_wei=portion)


def _passive(spendable_usdc: int, link: int, activity: float | None, change: float | None) -> Decision:
    direction, reason = _direction(activity, change)
    size = config.SWAP_MIN_USDC_UNITS

    if direction == 0:
        return _hold("PASSIVE waits. " + reason)

    # Contrarian: PASSIVE takes the other side of the trend.
    if direction < 0:
        if spendable_usdc < size:
            return _hold(f"PASSIVE would buy the dip but holds only {spendable_usdc} USDC units spendable")
        return Decision(
            "BUY_LINK", "PASSIVE buys weakness, contrarian to the Graph signal. " + reason,
            size_usdc_units=size,
        )

    if link <= 0:
        return _hold("PASSIVE would sell into strength but holds no LINK")
    portion = int(link * 0.03)
    if portion <= 0:
        return _hold("PASSIVE sell size rounded to zero")
    return Decision(
        "SELL_LINK", "PASSIVE sells strength, contrarian to the Graph signal. " + reason,
        size_link_wei=portion,
    )


def _rebalance(
    usdc: int, link: int, spendable_usdc: int, reserves: dict[str, int], change: float
) -> Decision:
    """
    Hold half the inventory in each leg, valued at the live pool rate. The Graph
    price tier decides how far to lean: a falling reference price shifts the
    target toward USDC, a rising one toward LINK.
    """
    r_usdc = reserves.get("usdc_units_6", 0)
    r_link = reserves.get("link_wei_18", 0)
    if r_usdc <= 0 or r_link <= 0:
        return _hold("REBALANCE has no pool reserves to value inventory against")

    # LINK valued in USDC units at the current pool rate.
    link_in_usdc = int(link * r_usdc / r_link) if r_link else 0
    total = usdc + link_in_usdc
    if total <= 0:
        return _hold("REBALANCE holds nothing to rebalance")

    link_share = link_in_usdc / total
    target = 0.5 + max(min(change * 5, 0.15), -0.15)
    drift = link_share - target

    if abs(drift) < REBALANCE_BAND:
        return _hold(
            f"REBALANCE inside band: LINK share {link_share:.3f} versus target "
            f"{target:.3f} set by the Graph price tier"
        )

    reason = (
        f"REBALANCE: LINK share {link_share:.3f}, target {target:.3f} from the "
        f"Graph price tier ({change * 100:+.2f} percent), drift {drift:+.3f}"
    )

    if drift < 0:
        size = _clamp_usdc(int(abs(drift) * total))
        if spendable_usdc < size:
            return _hold(reason + f", but only {spendable_usdc} USDC units spendable")
        return Decision("BUY_LINK", reason, size_usdc_units=size)

    # Overweight LINK: sell the excess, capped by the per-swap ceiling in USDC terms.
    excess_usdc = _clamp_usdc(int(drift * total))
    portion = int(excess_usdc * r_link / r_usdc) if r_usdc else 0
    portion = min(portion, link)
    if portion <= 0:
        return _hold(reason + ", but the sell size rounded to zero")
    return Decision("SELL_LINK", reason, size_link_wei=portion)
