import os
from pyngrok import ngrok, conf
import uvicorn
import asyncio
from upwork_job_processor import app
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def start_server():
    # Configure ngrok
    ngrok_auth_token = os.getenv("NGROK_AUTH_TOKEN")
    if not ngrok_auth_token:
        raise ValueError("NGROK_AUTH_TOKEN not found in environment variables")
    
    # Set the auth token
    conf.get_default().auth_token = ngrok_auth_token
    
    try:
        # Start ngrok tunnel
        http_tunnel = ngrok.connect(8000)
        public_url = http_tunnel.public_url
        
        print(f"\nNgrok tunnel established:")
        print(f"Public URL: {public_url}/webhook/upwork-jobs")
        print("Use this URL in your Chrome Extension")
        
        # Run the FastAPI app
        config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()
    except Exception as e:
        print(f"Error starting server: {str(e)}")
        # Clean up ngrok tunnels if there's an error
        ngrok.kill()
        raise

if __name__ == "__main__":
    try:
        asyncio.run(start_server())
    except KeyboardInterrupt:
        print("\nShutting down server...")
        ngrok.kill()
    except Exception as e:
        print(f"Server error: {str(e)}")
        ngrok.kill() 