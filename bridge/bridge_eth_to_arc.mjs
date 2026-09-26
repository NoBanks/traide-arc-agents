// bridge_eth_to_arc.mjs - move the deployer's USDC from Ethereum mainnet to Arc mainnet
// with Circle CCTP via Bridge Kit. The Forwarding Service mints on Arc, so the deployer
// needs no Arc gas up front. Key is read from ../.env and never printed.
//   node bridge_eth_to_arc.mjs <amount>          e.g. 12.90
import { readFileSync } from "node:fs";
import { BridgeKit } from "@circle-fin/bridge-kit";
import { Ethereum, Arc } from "@circle-fin/bridge-kit/chains";
import { createViemAdapterFromPrivateKey } from "@circle-fin/adapter-viem-v2";
import { createPublicClient, http, custom } from "viem";

// 2026-09-26: the default Ethereum client quoted a 0 gwei priority fee, so the first
// approve sat unmined until it was replaced by hand. This client answers
// eth_maxPriorityFeePerGas with 1 gwei on Ethereum mainnet (chain 1) only. DO NOT REMOVE.
const ETH_RPC = "https://ethereum-rpc.publicnode.com";
const ethTransport = http(ETH_RPC);
function publicClientFor(chain) {
  if (chain.id !== 1) return createPublicClient({ chain, transport: http() });
  const base = ethTransport({ chain });
  return createPublicClient({
    chain,
    transport: custom({
      async request({ method, params }) {
        if (method === "eth_maxPriorityFeePerGas") return "0x3b9aca00";
        return base.request({ method, params });
      },
    }),
  });
}

const env = Object.fromEntries(
  readFileSync(new URL("../.env", import.meta.url), "utf8")
    .split("\n").filter((l) => l.includes("=")).map((l) => [l.slice(0, l.indexOf("=")), l.slice(l.indexOf("=") + 1).trim()])
);
const amount = process.argv[2];
if (!amount) throw new Error("usage: node bridge_eth_to_arc.mjs <amount>");

const adapter = createViemAdapterFromPrivateKey({
  privateKey: env.ARC_DEPLOYER_PRIVATE_KEY,
  capabilities: { addressContext: "user-controlled", supportedChains: [Ethereum, Arc] },
  getPublicClient: ({ chain }) => publicClientFor(chain),
});
const recipient = "0xcEDdA90b60748e04Ff9C4123c5f49544611748e5";
const kit = new BridgeKit();
const result = await kit.bridge({
  from: { adapter, chain: "Ethereum" },
  to: { chain: "Arc", recipientAddress: recipient, useForwarder: true },
  amount,
});
console.log(JSON.stringify(result, (k, v) => (typeof v === "bigint" ? v.toString() : v), 2));
