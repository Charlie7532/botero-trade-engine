#!/usr/bin/env python3
"""
BOTERO TRADE ENGINE — Autonomous Execution Daemon
====================================================
The main loop that runs the trading engine during market hours.

Schedule (all times ET):
  09:30  Market Opens
  09:45  Fetch UW whale data → inject into hub
  09:50  run_core_scan() — S&P500 + Guru Gems
  10:00  First check_positions() — trailing stops
  ...    Every 5 min: check_positions()
  14:00  run_tactical_scan() — momentum movers
  15:30  Last check_positions()
  16:00  Market Closes → daily summary

Flags:
  --dry-run    Evaluate without sending orders (logs only)
  --once       Run one full cycle and exit
  --ticker X   Evaluate a single ticker and exit

Usage:
  python3 scripts/run_botero.py
  python3 scripts/run_botero.py --dry-run --once
  python3 scripts/run_botero.py --ticker NVDA
"""
import sys
import os
import signal
import logging
import argparse
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Setup path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend'))

from dotenv import load_dotenv
load_dotenv()

from application.paper_trading import PaperTradingOrchestrator
from infrastructure.data_providers.uw_data_bridge import UWDataBridge

# ═══════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════

ET = ZoneInfo("America/New_York")
CHECK_INTERVAL_MINUTES = 5
CORE_SCAN_HOUR = 9
CORE_SCAN_MINUTE = 50
TACTICAL_SCAN_HOUR = 14
TACTICAL_SCAN_MINUTE = 0
UW_REFRESH_MINUTES = 15  # Refresh whale data every 15 min

CORE_NOTIONAL = 8000.0
TACTICAL_NOTIONAL = 2000.0
MAX_CORE_POSITIONS = 5
MAX_TACTICAL_POSITIONS = 3

# Logging
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)


def setup_logging(dry_run: bool = False):
    """Configure dual logging: console + rotating file."""
    log_file = os.path.join(LOG_DIR, f"botero_{datetime.now().strftime('%Y-%m-%d')}.log")
    
    fmt = "%(asctime)s | %(levelname)-7s | %(message)s"
    datefmt = "%H:%M:%S"
    
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ]
    
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        datefmt=datefmt,
        handlers=handlers,
    )
    
    # Suppress noisy loggers
    logging.getLogger('yfinance').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('pymongo').setLevel(logging.WARNING)
    
    mode = "DRY-RUN" if dry_run else "LIVE"
    logging.info(f"═══ BOTERO TRADE ENGINE — {mode} MODE ═══")
    logging.info(f"Log file: {log_file}")


# ═══════════════════════════════════════════════════════════
# MARKET HOURS
# ═══════════════════════════════════════════════════════════

def is_market_open() -> bool:
    """Check if US stock market is currently open (9:30-16:00 ET, weekdays)."""
    now = datetime.now(ET)
    
    # Weekend
    if now.weekday() >= 5:
        return False
    
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    
    return market_open <= now <= market_close


def next_market_open() -> datetime:
    """Calculate when the market next opens."""
    now = datetime.now(ET)
    target = now.replace(hour=9, minute=30, second=0, microsecond=0)
    
    if now >= target:
        target += timedelta(days=1)
    
    # Skip weekends
    while target.weekday() >= 5:
        target += timedelta(days=1)
    
    return target


def time_until_market_open() -> float:
    """Seconds until next market open."""
    return (next_market_open() - datetime.now(ET)).total_seconds()


# ═══════════════════════════════════════════════════════════
# MAIN ENGINE CLASS
# ═══════════════════════════════════════════════════════════

class BoteroEngine:
    """Autonomous trading engine with market-hours awareness."""
    
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.running = True
        self.orchestrator = PaperTradingOrchestrator()
        self.uw_bridge = UWDataBridge()
        self.logger = logging.getLogger("BoteroEngine")
        
        # Track what we've done today
        self._core_scan_done_today = False
        self._tactical_scan_done_today = False
        self._last_uw_refresh = None
        self._last_check_positions = None
        self._today = None
        
        # Graceful shutdown
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)
    
    def _handle_shutdown(self, signum, frame):
        self.logger.info("🛑 Shutdown signal received — completing current cycle...")
        self.running = False
    
    def _new_day(self):
        """Reset daily trackers."""
        today = datetime.now(ET).date()
        if self._today != today:
            self._today = today
            self._core_scan_done_today = False
            self._tactical_scan_done_today = False
            self.logger.info(f"📅 New trading day: {today}")
    
    # ═══════════════════════════════════════════════════════════
    # DATA REFRESH
    # ═══════════════════════════════════════════════════════════
    
    def refresh_whale_data(self):
        """Fetch fresh UW data and inject into orchestrator."""
        if not self.uw_bridge.is_configured():
            self.logger.debug("UW API not configured — skipping whale data refresh")
            return
        
        now = datetime.now(ET)
        if (self._last_uw_refresh and 
            (now - self._last_uw_refresh).total_seconds() < UW_REFRESH_MINUTES * 60):
            return  # Too soon
        
        self.logger.info("🐋 Refreshing whale data from Unusual Whales API...")
        try:
            data = self.uw_bridge.fetch_all()
            self.orchestrator.inject_whale_data(**data)
            self._last_uw_refresh = now
            self.logger.info(
                f"🐋 Whale data injected: "
                f"{len(data['spy_ticks'])} SPY ticks, "
                f"{len(data['flow_alerts'])} alerts, "
                f"{len(data['tide_data'])} tide points"
            )
        except Exception as e:
            self.logger.error(f"❌ Failed to fetch UW data: {e}")
    
    # ═══════════════════════════════════════════════════════════
    # SCAN METHODS
    # ═══════════════════════════════════════════════════════════
    
    def run_core_scan(self):
        """Run the core (Hohn mode) scan for S&P500 + Guru Gems."""
        if self._core_scan_done_today:
            return
        
        now = datetime.now(ET)
        if now.hour < CORE_SCAN_HOUR or (now.hour == CORE_SCAN_HOUR and now.minute < CORE_SCAN_MINUTE):
            return
        
        self.logger.info("═══ CORE SCAN (Christopher Hohn Mode) ═══")
        
        if self.dry_run:
            self.logger.info("   [DRY-RUN] Core scan would execute here")
            self._core_scan_done_today = True
            return
        
        try:
            result = self.orchestrator.run_core_scan(
                max_positions=MAX_CORE_POSITIONS,
                notional_per_trade=CORE_NOTIONAL,
            )
            self.logger.info(f"   Core scan result: {result.get('status', 'unknown')}")
            trades = result.get('trades', [])
            for t in trades:
                action = t.get('action', 'unknown')
                ticker = t.get('ticker', '?')
                self.logger.info(f"   → {action}: {ticker}")
        except Exception as e:
            self.logger.error(f"❌ Core scan failed: {e}")
        
        self._core_scan_done_today = True
    
    def run_tactical_scan(self):
        """Run tactical (momentum) scan for afternoon movers."""
        if self._tactical_scan_done_today:
            return
        
        now = datetime.now(ET)
        if now.hour < TACTICAL_SCAN_HOUR or (now.hour == TACTICAL_SCAN_HOUR and now.minute < TACTICAL_SCAN_MINUTE):
            return
        
        self.logger.info("═══ TACTICAL SCAN (Eifert/Tudor Jones Mode) ═══")
        
        if self.dry_run:
            self.logger.info("   [DRY-RUN] Tactical scan would execute here")
            self._tactical_scan_done_today = True
            return
        
        try:
            result = self.orchestrator.run_tactical_scan(
                max_positions=MAX_TACTICAL_POSITIONS,
                notional_per_trade=TACTICAL_NOTIONAL,
            )
            self.logger.info(f"   Tactical scan result: {result.get('status', 'unknown')}")
        except Exception as e:
            self.logger.error(f"❌ Tactical scan failed: {e}")
        
        self._tactical_scan_done_today = True
    
    # ═══════════════════════════════════════════════════════════
    # POSITION MANAGEMENT
    # ═══════════════════════════════════════════════════════════
    
    def check_positions(self):
        """Review all open positions for exit signals."""
        now = datetime.now(ET)
        if (self._last_check_positions and 
            (now - self._last_check_positions).total_seconds() < CHECK_INTERVAL_MINUTES * 60):
            return  # Too soon
        
        self.logger.info("📊 Checking positions...")
        
        try:
            evaluations = self.orchestrator.check_positions()
            
            for ev in evaluations:
                if 'error' in ev:
                    continue
                
                ticker = ev.get('ticker', '?')
                pnl = ev.get('unrealized_pnl_pct', 0)
                stop = ev.get('trailing_stop', 0)
                frozen = ev.get('stop_frozen', False)
                exit_sig = ev.get('exit_signal', {})
                
                status = "🧊 FROZEN" if frozen else f"Stop=${stop:.2f}"
                should_exit = exit_sig.get('should_exit', False)
                
                emoji = "📈" if pnl > 0 else "📉"
                self.logger.info(
                    f"   {emoji} {ticker}: {pnl:+.1f}% | {status}"
                    + (f" | ⚠️ EXIT SIGNAL: {exit_sig.get('reason', '')}" if should_exit else "")
                )
                
                # Auto-close if exit signal fires
                if should_exit and not self.dry_run:
                    reason = exit_sig.get('reason', 'SYSTEM_EXIT')
                    self.logger.warning(f"   🚨 Auto-closing {ticker}: {reason}")
                    try:
                        self.orchestrator.close_position(
                            ticker=ticker,
                            exit_reason=reason,
                        )
                    except Exception as e:
                        self.logger.error(f"   ❌ Failed to close {ticker}: {e}")
            
            self._last_check_positions = now
            
        except Exception as e:
            self.logger.error(f"❌ check_positions failed: {e}")
    
    # ═══════════════════════════════════════════════════════════
    # DAILY SUMMARY
    # ═══════════════════════════════════════════════════════════
    
    def daily_summary(self):
        """Generate end-of-day summary."""
        self.logger.info("═══ DAILY SUMMARY ═══")
        
        try:
            account = self.orchestrator.get_account_status()
            if 'error' not in account:
                self.logger.info(f"   💰 Equity: ${account['equity']:,.2f}")
                self.logger.info(f"   💵 Cash: ${account['cash']:,.2f}")
                self.logger.info(f"   📊 Positions: {account['num_positions']}")
                self.logger.info(f"   🏢 Core: ${account.get('core_exposure', 0):,.0f}")
                self.logger.info(f"   🔥 Tactical: ${account.get('tactical_exposure', 0):,.0f}")
                
                for p in account.get('positions', []):
                    emoji = "📈" if p['unrealized_pnl'] > 0 else "📉"
                    self.logger.info(
                        f"   {emoji} {p['ticker']}: {p['unrealized_pnl_pct']:+.1f}% "
                        f"(${p['unrealized_pnl']:+,.0f})"
                    )
            
            # Performance stats
            perf = self.orchestrator.journal.get_performance_summary()
            if perf.get('total_trades', 0) > 0:
                self.logger.info(f"   📈 All-time: {perf['total_trades']} trades, "
                               f"WR={perf['win_rate']:.0f}%, PF={perf['profit_factor']:.2f}")
        except Exception as e:
            self.logger.error(f"Summary error: {e}")
    
    # ═══════════════════════════════════════════════════════════
    # SINGLE TICKER EVALUATION
    # ═══════════════════════════════════════════════════════════
    
    def evaluate_ticker(self, ticker: str):
        """Run the full EntryIntelligenceHub on a single ticker and display results."""
        self.logger.info(f"═══ EVALUATING {ticker} ═══")
        
        # Refresh whale data first
        self.refresh_whale_data()
        
        try:
            report = self.orchestrator.entry_hub.evaluate(ticker)
            
            self.logger.info(f"   Price:     ${report.current_price:.2f}")
            self.logger.info(f"   VIX:       {report.vix:.1f}")
            self.logger.info(f"   Phase:     {report.phase}")
            self.logger.info(f"   Gamma:     {report.gamma_regime}")
            self.logger.info(f"   Wyckoff:   {report.wyckoff_state}")
            self.logger.info(f"   Whales:    {report.whale_verdict}")
            self.logger.info(f"   R:R:       {report.risk_reward}:1")
            self.logger.info(f"   Dims:      {report.dimensions_confirming}/3")
            self.logger.info(f"   ─── VERDICT: {report.final_verdict} ───")
            self.logger.info(f"   {report.final_reason}")
            
            if report.entry_price > 0:
                self.logger.info(f"   Entry:  ${report.entry_price:.2f}")
                self.logger.info(f"   Stop:   ${report.stop_price:.2f}")
                self.logger.info(f"   Target: ${report.target_price:.2f}")
            
            return report
            
        except Exception as e:
            self.logger.error(f"❌ Evaluation failed for {ticker}: {e}")
            return None
    
    # ═══════════════════════════════════════════════════════════
    # MAIN LOOP
    # ═══════════════════════════════════════════════════════════
    
    def run_once(self):
        """Execute one full trading cycle."""
        self._new_day()
        self.refresh_whale_data()
        self.run_core_scan()
        self.check_positions()
        self.run_tactical_scan()
        self.daily_summary()
    
    def run(self):
        """
        Main autonomous loop.
        Runs during market hours, sleeps outside.
        """
        self.logger.info("🚀 Botero Trade Engine starting...")
        self.logger.info(f"   Mode: {'DRY-RUN' if self.dry_run else 'LIVE PAPER TRADING'}")
        self.logger.info(f"   UW API: {'✅ Configured' if self.uw_bridge.is_configured() else '❌ Not configured'}")
        self.logger.info(f"   Check interval: {CHECK_INTERVAL_MINUTES} min")
        self.logger.info(f"   Core scan: {CORE_SCAN_HOUR}:{CORE_SCAN_MINUTE:02d} ET")
        self.logger.info(f"   Tactical scan: {TACTICAL_SCAN_HOUR}:{TACTICAL_SCAN_MINUTE:02d} ET")
        
        while self.running:
            self._new_day()
            
            if not is_market_open():
                wait = time_until_market_open()
                # Cap wait to 1 hour chunks so we can catch SIGINT
                wait = min(wait, 3600)
                next_open = next_market_open()
                self.logger.info(
                    f"💤 Market closed. Next open: {next_open.strftime('%a %H:%M ET')} "
                    f"(sleeping {wait/3600:.1f}h)"
                )
                time.sleep(wait)
                continue
            
            now = datetime.now(ET)
            self.logger.info(f"⏰ Market open — {now.strftime('%H:%M ET')}")
            
            # Refresh whale data
            self.refresh_whale_data()
            
            # Run scans at their scheduled times
            self.run_core_scan()
            self.run_tactical_scan()
            
            # Check positions
            self.check_positions()
            
            # End-of-day summary
            if now.hour >= 15 and now.minute >= 45:
                self.daily_summary()
            
            # Sleep until next check
            self.logger.debug(f"   Next check in {CHECK_INTERVAL_MINUTES} min")
            for _ in range(CHECK_INTERVAL_MINUTES * 60):
                if not self.running:
                    break
                time.sleep(1)
        
        self.logger.info("🛑 Botero Trade Engine stopped.")


# ═══════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Botero Trade Engine — Autonomous Execution Daemon"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Evaluate without sending orders"
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Run one full cycle and exit"
    )
    parser.add_argument(
        "--ticker", type=str, default=None,
        help="Evaluate a single ticker and exit"
    )
    args = parser.parse_args()
    
    setup_logging(dry_run=args.dry_run)
    engine = BoteroEngine(dry_run=args.dry_run)
    
    if args.ticker:
        engine.evaluate_ticker(args.ticker.upper())
    elif args.once:
        engine.run_once()
    else:
        engine.run()


if __name__ == "__main__":
    main()
