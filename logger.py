"""
logger.py

Component 19 — Centralised logging factory.

Creates one plain-text log file per query run and one per conflict run.
All pipeline components accept an optional `logger` parameter — pass
None (the default) to disable logging. Existing tests are unaffected.

Log location:
    logs/query_YYYYMMDD_HHMMSS.log
    logs/conflict_<Company>_<Section>_YYYYMMDD_HHMMSS.log

Log format (plain text, human-readable):
    2026-04-30 14:30:22 [INFO ] RETRIEVER | ENTER | query="..."
    2026-04-30 14:30:23 [ERROR] RETRIEVER | EXCEPTION | ValueError: ...

Usage:
    from logger import setup_query_logger, setup_conflict_logger

    log = setup_query_logger("What were Apple's risk factors in 2022?")
    log = setup_conflict_logger("Apple", "Item 1A", 2020, 2023)
"""

import logging
import os
from datetime import datetime

LOG_DIR   = "logs"
_FORMAT   = "%(asctime)s [%(levelname)-5s] %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


def _build_logger(name: str, filepath: str) -> logging.Logger:
    """
    Internal factory. Returns a named logger writing plain text to `filepath`.
    propagate=False prevents Streamlit's root logger from capturing these records.
    Each call clears stale handlers so re-use of the same name is safe.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Clear stale handlers — guards against duplicate output if the logger
    # name is somehow reused within the same Python process.
    if logger.handlers:
        logger.handlers.clear()

    fh = logging.FileHandler(filepath, mode="w", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FMT))
    logger.addHandler(fh)
    logger.propagate = False

    return logger


def setup_query_logger(query: str) -> logging.Logger:
    """
    Creates logs/query_YYYYMMDD_HHMMSS.log.
    Call once per query submission from ui/app.py — before the pipeline runs.
    """
    os.makedirs(LOG_DIR, exist_ok=True)
    ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(LOG_DIR, f"query_{ts}.log")
    logger   = _build_logger(f"sec_rag_query_{ts}", filepath)

    logger.info("=" * 60)
    logger.info(f"PIPELINE | query_start | query={query!r}")
    logger.info("=" * 60)
    return logger


def setup_conflict_logger(
    company: str,
    section: str,
    start_year: int,
    end_year: int,
) -> logging.Logger:
    """
    Creates logs/conflict_<Company>_<Section>_YYYYMMDD_HHMMSS.log.
    Call once per conflict run from ui/app.py — before analyze_conflicts().
    """
    os.makedirs(LOG_DIR, exist_ok=True)
    ts           = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_section = section.replace(" ", "")
    filepath     = os.path.join(LOG_DIR, f"conflict_{company}_{safe_section}_{ts}.log")
    logger       = _build_logger(f"sec_rag_conflict_{ts}", filepath)

    logger.info("=" * 60)
    logger.info(f"PIPELINE | conflict_start | company={company!r} section={section!r} years={start_year}-{end_year}")
    logger.info("=" * 60)
    return logger
