import json
import logging
import os
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import openai
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from openai import OpenAI
from pyairtable import Api
from pyairtable import Table as Airtable
from pydantic import BaseModel, Field, RootModel
from slack_sdk import WebClient

from prompts.job_scoring import SYSTEM_MESSAGE, format_job_details
from prompts.proposal_generation import \
    SYSTEM_MESSAGE as PROPOSAL_SYSTEM_MESSAGE
from prompts.proposal_generation import \
    format_job_details as format_proposal_details

# Set up logging
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
log_file = log_dir / f"upwork_processor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()  # This will also print to console
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
logger.info("Environment variables loaded")

# Initialize FastAPI app
app = FastAPI(title="Upwork Job Processor")

async def get_airtable_schema() -> Dict[str, str]:
    """
    Fetch Airtable table schema and return column IDs
    """
    try:
        logger.info("Fetching Airtable schema...")
        
        # Get table metadata using the correct API methods
        base_id = os.getenv("AIRTABLE_BASE_ID")
        table_name = os.getenv("AIRTABLE_TABLE_NAME")
        
        # First, get a single record to analyze its structure
        records = airtable.all(max_records=1)
        if not records:
            raise ValueError("No records found in Airtable to analyze schema")
            
        # Extract field names from the first record
        sample_record = records[0]
        fields = sample_record.get('fields', {})
        
        # Map field names to their normalized versions
        column_ids = {}
        for field_name in fields.keys():
            normalized_name = field_name.upper().replace(' ', '_')
            column_ids[normalized_name] = field_name  # Store original field name
            logger.debug(f"Found field: {field_name} -> {normalized_name}")
        
        # Add known field mappings
        known_fields = {
            'URL': 'url',
            'TITLE': 'title',
            'DESCRIPTION': 'description',
            'SCORE': 'Score',
            'PROPOSAL': 'Proposal',
            'BUDGET': 'budget',
            'HOURLY_RANGE': 'hourlyRange',
            'ESTIMATED_TIME': 'estimatedTime',
            'SKILLS': 'skills'
        }
        
        # Update column_ids with known fields if they're not already present
        for key, value in known_fields.items():
            if key not in column_ids:
                column_ids[key] = value
                logger.debug(f"Added known field mapping: {key} -> {value}")
        
        logger.info("Successfully fetched Airtable schema")
        logger.debug(f"Final column mappings: {json.dumps(column_ids, indent=2)}")
        return column_ids
        
    except Exception as e:
        logger.error(f"Error fetching Airtable schema: {str(e)}", exc_info=True)
        raise

# Initialize clients
try:
    client = OpenAI()
    
    # Initialize Airtable client with validation
    airtable_api_key = os.getenv("AIRTABLE_API_KEY")
    base_id = os.getenv("AIRTABLE_BASE_ID")
    table_id = os.getenv("AIRTABLE_TABLE_ID")
    
    if not all([airtable_api_key, base_id, table_id]):
        raise ValueError("Missing required Airtable environment variables")
    
    # Initialize Airtable API client
    airtable_api = Api(airtable_api_key)
    base = airtable_api.base(base_id)
    airtable = base.table(table_id)
    
    # Test Airtable connection and get field names
    try:
        # First try to list tables to verify base access
        test_records = airtable.all(max_records=1, view=os.getenv("AIRTABLE_VIEW_ID"))
        logger.info("Successfully connected to Airtable")
        
        if test_records:
            sample_record = test_records[0]
            logger.debug(f"Sample record structure: {json.dumps(sample_record, indent=2)}")
            
            # Get field names from the record
            field_names = sample_record.get('fields', {}).keys()
            logger.info(f"Available fields: {', '.join(field_names)}")
        else:
            logger.warning("No existing records found in Airtable")
            
    except Exception as e:
        logger.error(f"Failed to access Airtable: {str(e)}")
        raise ValueError(f"Airtable access test failed: {str(e)}")

    # Initialize other clients
    slack_client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))
    logger.info("All clients initialized successfully")
    
except Exception as e:
    logger.error(f"Error initializing clients: {str(e)}", exc_info=True)
    raise

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

async def score_job(job: UpworkJob) -> int:
    """Score a job using OpenAI GPT-4 based on match criteria"""
    try:
        logger.info(f"Starting job scoring for: {job.title}")
        job_details = format_job_details(job)
        logger.debug(f"Formatted job details: {job_details}")

        # Using gpt-4o-mini as specified in Make.com blueprint
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Changed back to gpt-4o-mini
            messages=[
                {"role": "system", "content": SYSTEM_MESSAGE},
                {"role": "user", "content": job_details}
            ],
            temperature=1.0,
            top_p=1.0,
            max_tokens=10,
            response_format={ "type": "text" }
        )
        
        logger.debug(f"OpenAI API response: {response}")
        
        try:
            score = int(response.choices[0].message.content.strip())
            logger.info(f"Raw score from GPT: {score}")
            
            if 1 <= score <= 100:
                logger.info(f"Valid score generated: {score}")
                return score
            else:
                logger.warning(f"Invalid score range: {score}, defaulting to 1")
                return 1
                
        except ValueError as e:
            logger.error(f"Error parsing score: {str(e)}")
            logger.error(f"Raw response: {response.choices[0].message.content}")
            return 1
            
    except Exception as e:
        logger.error(f"Error in score_job: {str(e)}", exc_info=True)
        return 1

async def update_airtable_score(record_id: str, score: int) -> None:
    """Update the job score in Airtable"""
    try:
        logger.info(f"Updating Airtable record {record_id} with score {score}")
        
        # First verify record exists
        try:
            record = airtable.get(record_id)
            logger.debug(f"Found existing record: {record}")
        except Exception as e:
            logger.error(f"Failed to find record {record_id}: {str(e)}")
            raise ValueError(f"Record {record_id} not found in Airtable")
        
        # Attempt update
        result = airtable.update(record_id, {
            AIRTABLE_COLUMN_IDS['SCORE']: score
        })
        
        logger.info(f"Successfully updated Airtable record")
        logger.debug(f"Airtable update result: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Error updating Airtable score: {str(e)}", exc_info=True)
        raise

async def generate_proposal(job: UpworkJob) -> str:
    """
    Generate a proposal using OpenAI GPT-4
    Returns a string containing the proposal
    """
    try:
        job_details = format_proposal_details(job)

        # Using gpt-4o-mini as specified in Make.com blueprint
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Changed back to gpt-4o-mini
            messages=[
                {"role": "system", "content": PROPOSAL_SYSTEM_MESSAGE},
                {"role": "user", "content": job_details}
            ],
            temperature=0.2,
            max_tokens=500
        )
        
        return response.choices[0].message.content.strip()
            
    except Exception as e:
        logger.error(f"Error generating proposal: {str(e)}")
        return ""

async def update_airtable_proposal(record_id: str, proposal: str) -> None:
    """Update the job proposal in Airtable"""
    try:
        logger.info(f"Updating Airtable record {record_id} with proposal")
        result = airtable.update(record_id, {
            AIRTABLE_COLUMN_IDS['PROPOSAL']: proposal  # Using column ID instead of name
        })
        logger.info(f"Successfully updated Airtable proposal")
        logger.debug(f"Airtable update result: {result}")
        return result
    except Exception as e:
        logger.error(f"Error updating Airtable proposal: {str(e)}", exc_info=True)
        raise

async def validate_airtable_record(record_id: str, job: UpworkJob) -> bool:
    """Validate that an Airtable record exists and is accessible"""
    try:
        try:
            # Try to get the record
            record = airtable.get(record_id)
            logger.info(f"Found existing record: {record_id}")
            return True
        except Exception as e:
            # If record doesn't exist, create it with initial data
            logger.info(f"Record {record_id} not found, creating new record")
            new_record = airtable.create({
                "URL": job.url,
                "Title": job.title,
                "Description": job.description,
                "Budget": job.budget,
                "Hourly Range": job.hourly_range,
                "Estimated Time": job.estimated_time,
                "Skills": job.skills
            })
            logger.info(f"Created new record: {new_record['id']}")
            return True
            
    except Exception as e:
        logger.error(f"Record validation failed for {record_id}: {str(e)}")
        return False

async def process_single_job(job: UpworkJob) -> Dict[str, Any]:
    """Process a single Upwork job"""
    try:
        logger.info(f"\nProcessing job: {job.title}")
        logger.info(f"Airtable Record ID: {job.airtable_record_id}")
        
        # First ensure the record exists or create it
        if not await validate_airtable_record(job.airtable_record_id, job):
            logger.error(f"Could not validate/create record: {job.airtable_record_id}")
            raise ValueError(f"Could not validate/create Airtable record: {job.airtable_record_id}")
        
        # Update job details in Airtable
        try:
            update_data = {
                "URL": job.url,
                "Title": job.title,
                "Description": job.description,
                "Budget": job.budget,
                "Hourly Range": job.hourly_range,
                "Estimated Time": job.estimated_time,
                "Skills": job.skills
            }
            airtable.update(job.airtable_record_id, update_data)
            logger.info("Updated job details in Airtable")
        except Exception as e:
            logger.error(f"Error updating job details in Airtable: {str(e)}")
            raise
        
        # Score the job
        score = await score_job(job)
        logger.info(f"Final job score: {score}")
        
        # Update score in Airtable
        await update_airtable_score(job.airtable_record_id, score)
        
        result = {
            "status": "success",
            "job_title": job.title,
            "airtable_record_id": job.airtable_record_id,
            "score": score
        }
        
        # Generate and save proposal if score is high enough
        if score > 24:
            logger.info(f"Score {score} > 24, generating proposal")
            proposal = await generate_proposal(job)
            if proposal:
                await update_airtable_proposal(job.airtable_record_id, proposal)
                result["proposal"] = proposal
                logger.info(f"Generated and saved proposal")
        
        return result
        
    except Exception as e:
        logger.error(f"Error processing job {job.title}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing job: {str(e)}")

@app.post("/webhook/upwork-jobs")
async def process_upwork_jobs(request: Request) -> Dict[str, Any]:
    """Process incoming Upwork job data from webhook"""
    try:
        raw_data = await request.json()
        logger.info("Received webhook data")
        logger.debug(f"Raw webhook data: {json.dumps(raw_data, indent=2)}")
        
        if not isinstance(raw_data, list):
            logger.error("Invalid data format: not a list")
            raise HTTPException(status_code=400, detail="Expected a JSON array of jobs")
        
        try:
            job_list = UpworkJobList.model_validate(raw_data)
            logger.info(f"Successfully validated {len(job_list.root)} jobs")
        except Exception as e:
            logger.error(f"Job validation error: {str(e)}")
            raise HTTPException(status_code=400, detail=f"Invalid job data format: {str(e)}")
        
        results = []
        for job in job_list.root:
            result = await process_single_job(job)
            results.append(result)
            logger.info(f"Processed job: {job.title}")
        
        logger.info(f"Successfully processed all jobs")
        return {
            "status": "success",
            "message": f"Processed {len(results)} jobs successfully",
            "results": results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "online", "message": "Upwork Job Processor is running"}

if __name__ == "__main__":
    import socket
    
    def is_port_in_use(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('0.0.0.0', port))
                return False
            except socket.error:
                return True
    
    print("Starting Upwork Job Processor server...")
    
    # Check if port is in use
    if is_port_in_use(8000):
        logger.error("Port 8000 is already in use. Please stop any running instances first.")
        print("\nTo find and stop the process using port 8000, run:")
        print("sudo lsof -i :8000")
        print("sudo kill -9 <PID>")
        exit(1)
    
    # Start the server
    uvicorn.run(app, host="0.0.0.0", port=8000) 