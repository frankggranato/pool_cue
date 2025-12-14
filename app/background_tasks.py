"""
Background Tasks for Pool Cue

Runs periodic tasks like:
- Queue confirmation SMS checking
- Timeout handling for unconfirmed players
"""
import threading
import time
import logging

logger = logging.getLogger(__name__)

_task_thread = None
_stop_event = threading.Event()


def confirmation_task_loop():
    """
    Background loop that runs confirmation checks every 30 seconds.
    """
    from .queue_confirmation import run_confirmation_cycle
    
    logger.info("Queue confirmation background task started")
    
    while not _stop_event.is_set():
        try:
            result = run_confirmation_cycle()
            
            if result.get('sms_sent') or result.get('bumped') or result.get('removed'):
                logger.info(f"Confirmation cycle: sent={result.get('sms_sent', 0)}, "
                           f"bumped={result.get('bumped', 0)}, removed={result.get('removed', 0)}")
            
            if result.get('errors'):
                for err in result['errors']:
                    logger.warning(f"Confirmation error: {err}")
                    
        except Exception as e:
            logger.error(f"Error in confirmation task: {e}")
        
        # Wait 30 seconds before next check
        _stop_event.wait(30)
    
    logger.info("Queue confirmation background task stopped")


def start_background_tasks(app):
    """
    Start background task threads.
    Call this after app initialization.
    """
    global _task_thread
    
    if _task_thread is not None and _task_thread.is_alive():
        logger.warning("Background tasks already running")
        return
    
    _stop_event.clear()
    
    # Start confirmation task in daemon thread
    _task_thread = threading.Thread(
        target=confirmation_task_loop,
        name="ConfirmationTask",
        daemon=True
    )
    _task_thread.start()
    
    logger.info("Background tasks started")


def stop_background_tasks():
    """Stop all background tasks gracefully."""
    global _task_thread
    
    _stop_event.set()
    
    if _task_thread and _task_thread.is_alive():
        _task_thread.join(timeout=5)
    
    _task_thread = None
    logger.info("Background tasks stopped")
