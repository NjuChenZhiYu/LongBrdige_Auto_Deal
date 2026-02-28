
import os
import sys
import time
import logging

# Setup logging to console
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add src to path
sys.path.append(os.getcwd())

logger.info("Importing src.web.app...")
try:
    from src.web.app import app, scheduler, option_monitor, llm_analyst
    logger.info("Import successful.")
except Exception as e:
    logger.error(f"Import failed: {e}")
    sys.exit(1)

logger.info("Checking Scheduler...")
if scheduler.running:
    logger.info("Scheduler is running.")
    jobs = scheduler.get_jobs()
    logger.info(f"Scheduled jobs: {[job.id for job in jobs]}")
else:
    logger.error("Scheduler is NOT running.")

logger.info("Checking Option Monitor...")
# Wait a bit for thread to start
time.sleep(2)
if option_monitor._is_running:
    logger.info("Option Monitor is running (subscribed).")
else:
    logger.warning("Option Monitor is NOT running (or connection failed). Check logs.")

logger.info("Checking LLM Analyst...")
if llm_analyst:
    logger.info("LLM Analyst initialized.")
else:
    logger.error("LLM Analyst NOT initialized.")

logger.info("Verification complete.")
