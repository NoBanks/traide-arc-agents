// swap_usdc_to_eurc_arc.mjs - buy the pool's EURC leg on Arc mainnet through Circle Swap Kit.
//   node swap_usdc_to_eurc_arc.mjs <usdcAmount>
import { readFileSync } from "node:fs";
import { SwapKit } from "@circle-fin/swap-kit";
import { Arc } from "@circle-fin/bridge-kit/chains";
import { createViemAdapterFromPrivateKey } from "@circle-fin/adapter-viem-v2";
const env = Object.fromEntries(readFileSync(new URL("../.env", import.meta.url), "utf8").split("\n").filter((l) => l.includes("=")).map((l) => [l.slice(0, l.indexOf("=")), l.slice(l.indexOf("=") + 1).trim()]));
const adapter = createViemAdapterFromPrivateKey({ privateKey: env.ARC_DEPLOYER_PRIVATE_KEY, capabilities: { addressContext: "user-controlled", supportedChains: [Arc] } });
const kit = new SwapKit();
const params = { from: { adapter, chain: "Arc" }, tokenIn: "USDC", tokenOut: "EURC", amountIn: process.argv[2] };
console.log("estimate", JSON.stringify(await kit.estimate(params), (k, v) => (typeof v === "bigint" ? v.toString() : v)));
const r = await kit.swap(params);
console.log(JSON.stringify(r, (k, v) => (typeof v === "bigint" ? v.toString() : v), 2));
