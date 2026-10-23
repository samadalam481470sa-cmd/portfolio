"""Start the Wholesale Hub:  python3 run.py"""
import logging

import uvicorn

from hub.config import CONFIG

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    print(f"Wholesale Hub: http://{CONFIG['host']}:{CONFIG['port']}")
    uvicorn.run("hub.api:app", host=CONFIG["host"], port=CONFIG["port"], log_level="warning")
