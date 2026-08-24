import asyncio
import argparse
import sys
import logging

from app.monitoring.logger import setup_logging
from app.services.collection_service import CollectionService

logger = logging.getLogger(__name__)

async def run_collect_once():
    service = CollectionService()
    try:
        await service.collect_once()
    finally:
        await service.close()

async def run_forever():
    service = CollectionService()
    try:
        await service.run_forever()
    except KeyboardInterrupt:
        logger.info("Collector stopped by user.")
    finally:
        await service.close()

def main():
    setup_logging()
    
    parser = argparse.ArgumentParser(description="Virtual League Collector")
    parser.add_argument("command", choices=["collect-once", "run", "status"], help="Command to run")
    
    args = parser.parse_args()
    
    if args.command == "collect-once":
        asyncio.run(run_collect_once())
    elif args.command == "run":
        asyncio.run(run_forever())
    elif args.command == "status":
        print("Collector status: READY")
        # In a real app, this would query the DB to show stats
        
if __name__ == "__main__":
    main()
