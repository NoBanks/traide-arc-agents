// PM2 config for traide-arc-agents.
//
// House crash-loop guards are mandatory here and must not be removed:
//   max_restarts             bounded restarts instead of an infinite loop
//   min_uptime 30000         a process that dies inside 30s counts as a crash
//   exp_backoff_restart_delay  backs off instead of hammering the RPC
//   autorestart true         but bounded by max_restarts above
// Logs stay in ~/.pm2/logs so pm2-logrotate can cap them.
//
// Start:   pm2 start ecosystem.config.js && pm2 save
// Status:  pm2 list | grep arc-agents
// Logs:    pm2 logs arc-agents-runner --lines 50 --nostream

const path = require("path");
const ROOT = __dirname;
const PY = "/opt/homebrew/bin/python3.11";

module.exports = {
  apps: [
    {
      name: "arc-agents-runner",
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
      },
    },
    {
      name: "arc-agents-dashboard",
      script: PY,
      args: ["-m", "arc_agents.dashboard"],
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
        DASHBOARD_PORT: "17360",
      },
    },
  ],
};
