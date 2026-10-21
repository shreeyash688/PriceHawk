"""Background thread that re-checks all active products every few seconds/minutes."""
import logging
import threading

from services import tracker_service

logger = logging.getLogger(__name__)


class PriceMonitor(threading.Thread):

    def __init__(self, interval_seconds):
        super().__init__(name="PriceMonitor", daemon=True)  # daemon: dies when the app closes
        self.interval_seconds = interval_seconds
        self._stop_event = threading.Event()

    def run(self):
        logger.info("Price monitor started (every %s seconds)", self.interval_seconds)
        # wait() sleeps, but wakes up instantly if stop() is called
        while not self._stop_event.wait(self.interval_seconds):
            try:
                checked = tracker_service.check_all_products()
                logger.info("Monitor round finished: %s product(s) checked", checked)
            except Exception:
                logger.exception("Monitor round crashed; will try again next round")

    def stop(self):
        self._stop_event.set()


_monitor = None


def start_monitor(interval_seconds):
    """Start the monitor ONCE. Calling this again does nothing, so workers never multiply."""
    global _monitor
    if _monitor is not None and _monitor.is_alive():
        return _monitor
    _monitor = PriceMonitor(interval_seconds)
    _monitor.start()
    return _monitor
