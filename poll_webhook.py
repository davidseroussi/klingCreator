import asyncio
import os
from dotenv import load_dotenv
from kling.api import poll_and_notify

async def main(task_id: int, webhook_url: str):
    await poll_and_notify(task_id, webhook_url)

if __name__ == "__main__":
    import argparse
    
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Poll video status and send webhook notifications')
    parser.add_argument('task_id', type=int, help='The task ID to poll')
    parser.add_argument('webhook_url', type=str, help='The webhook URL to notify')
    
    # Parse arguments
    args = parser.parse_args()
    
    # Load environment variables
    load_dotenv()
    
    # Run the async function
    asyncio.run(main(args.task_id, args.webhook_url)) 