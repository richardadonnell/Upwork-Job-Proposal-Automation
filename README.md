# Upwork-Job-Proposal-Automation

## Overview

This project automates the process of sending job proposals on Upwork. It leverages several APIs and services to streamline the workflow, including OpenAI for generating proposal content, Airtable for storing job data, Slack for notifications, and ngrok for exposing the local server to the internet.

## Features

- **OpenAI Integration**: Uses OpenAI's API to generate job proposals based on job descriptions.
- **Airtable Integration**: Stores and retrieves job data from Airtable.
- **Slack Integration**: Sends notifications to a Slack channel when new job proposals are sent.
- **Ngrok Integration**: Exposes the local server to the internet for webhook handling.

## Setup

### Prerequisites

- Python 3.10 or later
- An OpenAI API key
- An Airtable API key, base ID, and table name
- A Slack bot token and channel ID
- An ngrok account and auth token

### Installation

1. Clone the repository:

   ```sh
   git clone https://github.com/yourusername/Upwork-Job-Proposal-Automation.git
   cd Upwork-Job-Proposal-Automation
   ```

2. Create a virtual environment and activate it:

   ```sh
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. Install the required packages:

   ```sh
   pip install -r requirements.txt
   ```

4. Copy the `.env.example` file to `.env` and fill in your credentials:
   ```sh
   cp .env.example .env
   ```

### Ngrok Setup

1. Sign up for an ngrok account at [ngrok.com](https://ngrok.com/).
2. After signing up, log in to your ngrok dashboard.
3. Navigate to the "Auth" section to find your ngrok auth token.
4. Copy the auth token and add it to your `.env` file under `NGROK_AUTH_TOKEN`.

### Running the Server

1. Start the server:

   ```sh
   python run_server.py
   ```

2. The server will start and ngrok will create a public URL. This URL will be saved in the `.env` file under `NGROK_PUBLIC_URL`.

3. Use the public URL in your Chrome Extension or any other client to interact with the server.

## Usage

- The server listens for incoming webhooks from Upwork.
- When a new job is posted, the server processes the job data, generates a proposal using OpenAI, and stores the job data in Airtable.
- A notification is sent to a specified Slack channel with the details of the job and the generated proposal.

### Testing with Example Job Data

To test the webhook with example job data, you can use the following `curl` command. This command sends a POST request to the local server with a JSON file containing job data:

```
curl -X POST http://localhost:8000/webhook/upwork-jobs \
  -H "Content-Type: application/json" \
  -d @example-hourly-job.json
```
