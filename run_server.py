import asyncio
import json
import os
from pathlib import Path

import requests
import uvicorn
from dotenv import load_dotenv, set_key

from upwork_job_processor import app, logger

# Load environment variables
load_dotenv()

async def create_ngrok_tunnel() -> str:
    """Create ngrok tunnel using API"""
    try:
        ngrok_api_key = os.getenv("NGROK_API_KEY")
        if not ngrok_api_key:
            raise ValueError("NGROK_API_KEY not found in environment variables")

        # API endpoint for creating tunnels
        url = "https://api.ngrok.com/tunnels"
        
        # Headers required by ngrok API
        headers = {
            "Authorization": f"Bearer {ngrok_api_key}",
            "Content-Type": "application/json",
            "Ngrok-Version": "2"
        }
        
        # Tunnel configuration
        data = {
            "forwards_to": "http://localhost:8000",
            "proto": "https"
        }
        
        # Create tunnel using API
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        
        # Extract public URL from response
        tunnel_data = response.json()
        logger.debug(f"Raw ngrok response: {json.dumps(tunnel_data, indent=2)}")
        
        # According to ngrok API docs, the URL should be in the following locations
        # Try each possible location
        public_url = None
        
        # Try direct URL field
        if 'url' in tunnel_data:
            public_url = tunnel_data['url']
        
        # Try public_url field
        elif 'public_url' in tunnel_data:
            public_url = tunnel_data['public_url']
            
        # Try endpoint URLs
        elif 'endpoints' in tunnel_data:
            endpoints = tunnel_data['endpoints']
            for endpoint in endpoints:
                if endpoint.get('proto') == 'https':
                    public_url = endpoint.get('url')
                    break
                    
        # Try tunnel URL
        elif 'tunnel' in tunnel_data and 'url' in tunnel_data['tunnel']:
            public_url = tunnel_data['tunnel']['url']
            
        if not public_url:
            logger.error(f"Could not find URL in response: {tunnel_data}")
            raise ValueError("No public URL found in ngrok response")
            
        # Ensure URL starts with https://
        if not public_url.startswith('https://'):
            public_url = f"https://{public_url}"
            
        logger.info(f"Successfully extracted ngrok URL: {public_url}")
        return public_url
        
    except Exception as e:
        logger.error(f"Error creating ngrok tunnel: {str(e)}")
        raise

async def delete_ngrok_tunnels():
    """Delete all active ngrok tunnels"""
    try:
        ngrok_api_key = os.getenv("NGROK_API_KEY")
        
        # Get list of active tunnels
        url = "https://api.ngrok.com/tunnels"
        headers = {
            "Authorization": f"Bearer {ngrok_api_key}",
            "Ngrok-Version": "2"
        }
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        # Delete each tunnel
        tunnels = response.json().get('tunnels', [])
        for tunnel in tunnels:
            tunnel_id = tunnel.get('id')
            if tunnel_id:
                delete_url = f"https://api.ngrok.com/tunnels/{tunnel_id}"
                requests.delete(delete_url, headers=headers)
                logger.info(f"Deleted tunnel: {tunnel_id}")
                
    except Exception as e:
        logger.error(f"Error deleting ngrok tunnels: {str(e)}")

async def start_server():
    try:
        # First, clean up any existing tunnels
        await delete_ngrok_tunnels()
        
        # Create new tunnel
        public_url = await create_ngrok_tunnel()
        if not public_url:
            raise ValueError("Failed to get public URL from ngrok")
            
        # Update .env file
        env_path = Path('.env')
        webhook_url = f"{public_url}/webhook/upwork-jobs"
        
        # First read existing content
        if env_path.exists():
            with open(env_path, 'r') as f:
                env_content = f.read()
        
        # Update URLs while preserving other variables
        set_key(env_path, "NGROK_PUBLIC_URL", public_url)
        set_key(env_path, "WEBHOOK_URL", webhook_url)
        
        # Verify the update
        load_dotenv()
        saved_url = os.getenv("NGROK_PUBLIC_URL")
        if saved_url != public_url:
            logger.warning(f"URL mismatch after save: Expected {public_url}, got {saved_url}")
        
        logger.info(f"Updated .env file with URLs:")
        logger.info(f"NGROK_PUBLIC_URL={public_url}")
        logger.info(f"WEBHOOK_URL={webhook_url}")
        
        # Print URLs for user
        print("\nNgrok tunnel established!")
        print("----------------------------------------")
        print(f"Public URL: {public_url}")
        print(f"Webhook URL: {webhook_url}")
        print("----------------------------------------")
        print("\nTo test the webhook, use this curl command:")
        print(f"curl -X POST {webhook_url} \\")
        print("  -H \"Content-Type: application/json\" \\")
        print("  -d @example-hourly-job.json")
        print("\nURLs have been saved to .env file")
        
        # Run the FastAPI app
        config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()
        
    except Exception as e:
        logger.error(f"Error starting server: {str(e)}")
        await delete_ngrok_tunnels()
        raise

if __name__ == "__main__":
    try:
        asyncio.run(start_server())
    except KeyboardInterrupt:
        print("\nShutting down server...")
        asyncio.run(delete_ngrok_tunnels())
    except Exception as e:
        print(f"Server error: {str(e)}")
        asyncio.run(delete_ngrok_tunnels()) 