import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import openai
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from pyairtable import Table as Airtable
from pydantic import BaseModel, Field, RootModel
from slack_sdk import WebClient

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(title="Upwork Job Processor")

# Initialize clients
openai.api_key = os.getenv("OPENAI_API_KEY")
airtable = Airtable(
    api_key=os.getenv("AIRTABLE_API_KEY"),
    base_id=os.getenv("AIRTABLE_BASE_ID"),
    table_name=os.getenv("AIRTABLE_TABLE_NAME")
)
slack_client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))

class UpworkJob(BaseModel):
    """Pydantic model for Upwork job data"""
    airtable_record_id: str
    created_time: datetime
    url: str
    title: str
    description: str
    budget: str = Field(default="N/A")
    hourly_range: str = Field(default="N/A")
    estimated_time: str = Field(default="N/A")
    skills: str = Field(default="")
    created_date: datetime
    proposal: str = Field(default="")

class UpworkJobList(RootModel[List[UpworkJob]]):
    """Pydantic model for list of Upwork jobs"""
    pass

async def process_single_job(job: UpworkJob) -> Dict[str, Any]:
    """
    Process a single Upwork job
    """
    try:
        # Log job details for debugging
        print(f"Processing job: {job.title}")
        print(f"Airtable Record ID: {job.airtable_record_id}")
        
        # TODO: Implement job processing steps
        # score = await score_job(job)
        # await update_airtable_score(job.airtable_record_id, score)
        
        # if score > 24:
        #     proposal = await generate_proposal(job)
        #     await update_airtable_proposal(job.airtable_record_id, proposal)
        #     await send_slack_notification(job, score, proposal)
        
        return {
            "status": "success",
            "job_title": job.title,
            "airtable_record_id": job.airtable_record_id
        }
        
    except Exception as e:
        print(f"Error processing job {job.title}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing job: {str(e)}")

@app.post("/webhook/upwork-jobs")
async def process_upwork_jobs(request: Request) -> Dict[str, Any]:
    """
    Process incoming Upwork job data from webhook
    """
    try:
        # Get the raw JSON data from the request
        raw_data = await request.json()
        
        # Log incoming data for debugging
        print("Received webhook data:", json.dumps(raw_data, indent=2))
        
        # Validate that we received a list
        if not isinstance(raw_data, list):
            raise HTTPException(status_code=400, detail="Expected a JSON array of jobs")
        
        # Parse the job list using Pydantic
        try:
            job_list = UpworkJobList.model_validate(raw_data)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid job data format: {str(e)}")
        
        # Process each job in the list
        results = []
        for job in job_list.root:
            result = await process_single_job(job)
            results.append(result)
        
        return {
            "status": "success",
            "message": f"Processed {len(results)} jobs successfully",
            "results": results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error processing webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "online", "message": "Upwork Job Processor is running"}

if __name__ == "__main__":
    print("Starting Upwork Job Processor server...")
    uvicorn.run(app, host="0.0.0.0", port=8000) 