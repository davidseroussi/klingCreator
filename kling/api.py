from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, HttpUrl
from typing import List, Optional
import asyncio
import httpx
import os
from dotenv import load_dotenv
from tempfile import NamedTemporaryFile
import traceback

from kling import VideoGen, TaskStatus

load_dotenv()
app = FastAPI()

KLING_COOKIE = os.getenv("KLING_COOKIE")
if not KLING_COOKIE:
    raise ValueError("KLING_COOKIE must be set in .env file")

class VideoRequest(BaseModel):
    prompt: str
    image_url: Optional[str] = None
    image_path: Optional[str] = None
    is_high_quality: bool = True
    auto_extend: bool = False
    model_name: str = "1.5"
    webhook_url: Optional[HttpUrl] = None

class VideoResponse(BaseModel):
    task_id: int

async def poll_and_notify(task_id: int, webhook_url: str):
    """Background task to poll video status and notify webhook"""
    generator = VideoGen(KLING_COOKIE)
    async with httpx.AsyncClient() as client:
        while True:
            try:
                # Use the existing fetch_metadata function
                data, status = generator.fetch_metadata(task_id)
                
                if status == TaskStatus.COMPLETED:
                    # Use same video URL fetching logic as get_video_status
                    works = data.get("works", [])
                    video_urls = []
                    for work in works:
                        work_id = work["workId"]
                        resource, _ = generator.fetch_video_url(work_id)
                        if resource:
                            video_urls.append(resource)
                    
                    await client.post(webhook_url, json={
                        "task_id": task_id,
                        "status": "completed",
                        "video_urls": video_urls
                    })
                    break
                    
                elif status == TaskStatus.FAILED:
                    await client.post(webhook_url, json={
                        "task_id": task_id,
                        "status": "failed",
                        "error": "Video generation failed"
                    })
                    break
                    
                # Still pending, wait before next check
                await asyncio.sleep(5)
                
            except Exception as e:
                await client.post(webhook_url, json={
                    "task_id": task_id,
                    "status": "error",
                    "error": str(e)
                })
                break

@app.post("/api/v1/create-video", response_model=VideoResponse)
async def create_video(request: VideoRequest, background_tasks: BackgroundTasks):
    try:
        generator = VideoGen(KLING_COOKIE)
        
        # Download image if URL is provided
        if request.image_url:
            async with httpx.AsyncClient() as client:
                response = await client.get(request.image_url)
                response.raise_for_status()
                
                # Try to get extension from content-type first
                content_type = response.headers.get('content-type', '')
                if 'image/jpeg' in content_type:
                    extension = '.jpg'
                elif 'image/png' in content_type:
                    extension = '.png'
                elif 'image/gif' in content_type:
                    extension = '.gif'
                elif 'image/webp' in content_type:
                    extension = '.webp'
                else:
                    # Fallback to getting extension from URL
                    from urllib.parse import urlparse
                    path = urlparse(str(request.image_url)).path
                    extension = os.path.splitext(path)[1] or '.jpg'  # fallback to .jpg if no extension found
                
                # Create and use a temporary file with correct extension
                with NamedTemporaryFile(suffix=extension, delete=False) as temp_file:
                    temp_file.write(response.content)
                    request.image_path = temp_file.name
                    request.image_url = None

        try:
            task_id = generator.get_video(
                prompt=request.prompt,
                image_url=None,  # Always None since we're using image_path
                image_path=request.image_path,
                is_high_quality=request.is_high_quality,
                model_name=request.model_name,
                _return_task_only=True
            )
        except Exception as e:
            print(f"Error: {e}")
            print("Stacktrace:")
            traceback.print_exc()
            raise HTTPException(status_code=400, detail=str(e))
        finally:
            # Clean up temporary file if it was created
            if request.image_path and request.image_url is None:  # Only delete if we created it
                os.remove(request.image_path)
        
        # Start background polling
        if request.webhook_url:
            background_tasks.add_task(poll_and_notify, task_id, str(request.webhook_url))
        
        return VideoResponse(task_id=task_id)
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/v1/video-status/{task_id}")
async def get_video_status(task_id: str):
    try:
        generator = VideoGen(KLING_COOKIE)
        data, status = generator.fetch_metadata(task_id)
        
        if status == TaskStatus.COMPLETED:
            works = data.get("works", [])
            video_urls = []
            for work in works:
                work_id = work["workId"]
                resource, _ = generator.fetch_video_url(work_id)
                if resource:
                    video_urls.append(resource)
        else:
            video_urls = []
            
        return {
            "task_id": task_id,
            "status": status.name.lower(),
            "video_urls": video_urls
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) 