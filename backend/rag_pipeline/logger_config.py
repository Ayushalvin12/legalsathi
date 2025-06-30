import logging
from logging.handlers import RotatingFileHandler
import os

def get_logger(name="rag_pipeline"):
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logs_dir = os.path.join(base_dir,"logs")
    os.makedirs(logs_dir, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        file_handler = RotatingFileHandler(
            os.path.join(logs_dir, "rag_pipeline.log"),
            maxBytes=10*1024*1024,
            backupCount=5
        )

        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.DEBUG)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger