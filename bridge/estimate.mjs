import { readFileSync } from "node:fs";
import { BridgeKit } from "@circle-fin/bridge-kit";
import { Ethereum, Arc } from "@circle-fin/bridge-kit/chains";
import { createViemAdapterFromPrivateKey } from "@circle-fin/adapter-viem-v2";
const env = Object.fromEntries(readFileSync(new URL("../.env", import.meta.url), "utf8").split("\n").filter((l) => l.includes("=")).map((l) => [l.slice(0, l.indexOf("=")), l.slice(l.indexOf("=") + 1).trim()]));
const adapter = createViemAdapterFromPrivateKey({ privateKey: env.ARC_DEPLOYER_PRIVATE_KEY, capabilities: { addressContext: "user-controlled", supportedChains: [Ethereum, Arc] } });
const kit = new BridgeKit();
const est = await kit.estimate({ from: { adapter, chain: "Ethereum" }, to: { chain: "Arc", recipientAddress: "0xcEDdA90b60748e04Ff9C4123c5f49544611748e5", useForwarder: true }, amount: process.argv[2] });
console.log(JSON.stringify(est, (k, v) => (typeof v === "bigint" ? v.toString() : v), 2));
