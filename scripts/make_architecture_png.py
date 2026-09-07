"""
make_architecture_png.py - render docs/architecture.png.

Arc's prize requires an architecture diagram in the README. This draws it from
code so it can be regenerated when the system changes, rather than being a
screenshot nobody can update.

    python3.11 -m scripts.make_architecture_png
"""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from arc_agents import config

BG = "#0d1117"
PANEL = "#161b22"
LINE = "#30363d"
FG = "#e6edf3"
DIM = "#8b949e"
GRAPH_C = "#7c5cff"
ARC_C = "#3fb950"
NEW_C = "#58a6ff"
OLD_C = "#8b949e"


def box(ax, x, y, w, h, title, lines, edge, dashed=False):
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.02,rounding_size=0.08",
            linewidth=1.6, edgecolor=edge, facecolor=PANEL,
            linestyle="--" if dashed else "-",
        )
    )
    ax.text(x + w / 2, y + h - 0.20, title, ha="center", va="top",
            color=FG, fontsize=10.5, fontweight="bold")
    for i, line in enumerate(lines):
        ax.text(x + w / 2, y + h - 0.46 - i * 0.20, line, ha="center", va="top",
                color=DIM, fontsize=7.6, family="monospace")


def arrow(ax, p1, p2, label="", color=LINE, style="-", offset=0.0):
    ax.add_patch(
        FancyArrowPatch(p1, p2, arrowstyle="-|>", mutation_scale=13,
                        linewidth=1.4, color=color, linestyle=style,
                        shrinkA=2, shrinkB=2)
    )
    if label:
        mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2 + offset
        ax.text(mx, my, label, ha="center", va="bottom", color=color,
                fontsize=7.4, fontweight="bold",
                bbox=dict(facecolor=BG, edgecolor="none", pad=1.4))


def main() -> int:
    fig, ax = plt.subplots(figsize=(13, 8.2), dpi=160)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 8.2)
    ax.axis("off")

    ax.text(0.35, 7.85, "TRAIDE agents on Arc", color=FG, fontsize=17, fontweight="bold", va="top")
    ax.text(0.35, 7.42,
            "Live Graph data decides. Arc executes. Every decision is a hashed receipt anchored on chain.",
            color=DIM, fontsize=9.4, va="top")

    # The Graph column
    box(ax, 0.35, 5.15, 3.5, 1.85, "THE GRAPH  (two products)",
        ["1 Token API, api.pinax.network",
         "  /v1/evm/dexes     keyless",
         "2 Subgraph, gateway.thegraph.com",
         "  tokenHourDatas    studio key",
         "live at query time, never cached"], GRAPH_C)

    box(ax, 0.35, 3.55, 3.5, 1.25, "GUARD",
        ["no live Graph signal",
         "  -> every agent HOLDs",
         "no key -> REBALANCE flat",
         "no other data source exists"], GRAPH_C, dashed=True)

    # Agents
    box(ax, 4.55, 4.55, 3.9, 2.45, "THREE AGENTS  (new)",
        ["PASSIVE     m/44'/60'/0'/0/1",
         "AGGRESSIVE  m/44'/60'/0'/0/2",
         "REBALANCE   m/44'/60'/0'/0/3",
         "",
         "own wallet, own key, own",
         "inventory, own decision"], NEW_C)

    box(ax, 4.55, 2.55, 3.9, 1.65, "KEEPER RECEIPT  (new shape)",
        ["type arc_agent_decision",
         "canonical JSON, sort_keys,",
         "separators (,:)  -> sha256",
         "carries Graph provenance:",
         "endpoint, params, status,",
         "response sha256, timestamp"], NEW_C)

    # Arc column
    box(ax, 9.15, 5.15, 3.5, 1.85, f"ARC TESTNET {config.CHAIN_ID}",
        ["TRAIDEAMM  0x4b6781Af...",
         "native USDC 0x3600...0000 (6d)",
         "LINKMock   0x4A8ac012... (18d)",
         "gas is paid in USDC",
         "swap() -> status 1 or nothing"], ARC_C)

    box(ax, 9.15, 3.05, 3.5, 1.65, "ArcReceiptAnchor  (new)",
        ["attest(bytes32,bytes32)",
         "indexed Attested event",
         "first seen block per hash",
         "no owner, no upgrade path"], ARC_C)

    box(ax, 9.15, 1.05, 3.5, 1.45, "DASHBOARD  (new)",
        ["FastAPI, read only, free",
         "127.0.0.1:17360",
         "wallets, swaps, receipts,",
         "anchors, P and L vs hold"], NEW_C)

    # Pre-existing
    box(ax, 0.35, 1.05, 3.5, 1.85, "PRE EXISTING",
        ["TRAIDE AMM fleet, 26 chains",
         "traide-keeper canonical hash",
         "clip_sim.py paper agents",
         "  (DexScreener, NOT used here)",
         "x402 paid intelligence API"], OLD_C, dashed=True)

    arrow(ax, (3.85, 6.05), (4.55, 6.05), "live signal", GRAPH_C, offset=0.08)
    arrow(ax, (3.85, 4.15), (4.55, 5.10), "refuse", GRAPH_C, style="--")
    arrow(ax, (8.45, 6.05), (9.15, 6.05), "real swap", ARC_C, offset=0.08)
    arrow(ax, (6.50, 4.55), (6.50, 4.20), "", NEW_C)
    arrow(ax, (8.45, 3.55), (9.15, 3.75), "sha256", ARC_C, offset=0.08)
    arrow(ax, (10.90, 5.15), (10.90, 4.70), "", ARC_C)
    arrow(ax, (10.90, 3.05), (10.90, 2.50), "", ARC_C)
    arrow(ax, (2.10, 2.90), (2.10, 3.55), "same hash rule", OLD_C, style="--", offset=0.06)

    ax.text(0.35, 0.55, "solid = event work    dashed = pre existing or a refusal path",
            color=DIM, fontsize=8)
    ax.text(12.65, 0.55, "MIT  github.com/NoBanks/traide-arc-agents",
            color=DIM, fontsize=8, ha="right")

    out = config.REPO_ROOT / "docs" / "architecture.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor=BG, bbox_inches="tight", pad_inches=0.25)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
