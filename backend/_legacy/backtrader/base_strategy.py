import backtrader as bt


class BaseStrategy(bt.Strategy):
    """Base strategy class for all Botero Trade strategies.

    Provides common infrastructure: logging, trade tracking, and
    a clean hook system so subclasses only implement signal logic.

    Usage:
        class MyStrategy(BaseStrategy):
            def next(self):
                if self.should_buy():
                    self.buy()

            def should_buy(self) -> bool:
                # your signal logic here
                return False
    """

    params = (
        ("log_trades", True),
    )

    def __init__(self):
        self.order = None
        self.trades_log: list[dict] = []

    def log(self, message: str):
        bar_datetime = self.datas[0].datetime.date(0)
        print(f"[{bar_datetime}] {self.__class__.__name__}: {message}")

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status == order.Completed:
            direction = "BUY" if order.isbuy() else "SELL"
            if self.params.log_trades:
                self.log(
                    f"{direction} executed — price: {order.executed.price:.2f}, "
                    f"size: {order.executed.size}, cost: {order.executed.value:.2f}, "
                    f"commission: {order.executed.comm:.2f}"
                )
            self.trades_log.append({
                "type": direction,
                "price": order.executed.price,
                "size": order.executed.size,
                "value": order.executed.value,
                "commission": order.executed.comm,
                "date": str(self.datas[0].datetime.date(0)),
            })
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f"Order {order.status}: {order.getstatusname()}")

        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return
        if self.params.log_trades:
            self.log(f"Trade closed — gross PnL: {trade.pnl:.2f}, net PnL: {trade.pnlcomm:.2f}")

    def next(self):
        raise NotImplementedError("Implement next() in your strategy subclass")
