// PM2 config for the Arc MAINNET agents (chain 5042). Separate from ecosystem.config.js,
// which runs testnet. Same house crash-loop guards; do not remove them.
// Cadence 10800s (3h): measured 0.0047 USDC of gas per trade (swap + anchor) on
// 2026-09-26, so a 3h cycle costs about 0.10 USDC/day for all three agents.
//
// Start:   pm2 start ecosystem.mainnet.config.js && pm2 save
// Logs:    pm2 logs arc-agents-mainnet-runner --lines 50 --nostream
const ROOT = __dirname;
const PY = "/opt/homebrew/bin/python3.11";

module.exports = {
  apps: [
    {
      name: "arc-agents-mainnet-runner",
      script: PY,
      args: ["-m", "arc_agents.runner"],
      cwd: ROOT,
      interpreter: "none",
      autorestart: true,
      max_restarts: 10,
      min_uptime: 30000,
      exp_backoff_restart_delay: 2000,
      restart_delay: 5000,
      max_memory_restart: "300M",
      kill_timeout: 10000,
      env: {
        PYTHONUNBUFFERED: "1",
        PYTHONPATH: ROOT,
        ARC_NETWORK: "mainnet",
        ARC_AGENT_CYCLE_SECONDS: "10800",
      },
    },
  ],
};
