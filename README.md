# SchoolCopilot 

An AI-powered assistant that helps parents manage school emails.

## Features

- Reads Gmail inbox emails
- Uses OpenAI structured outputs with Pydantic
- Categorizes emails by priority
- Sends urgent notifications using Pushover
- Tracks notification acknowledgements
- Stores processed emails in SQLite
- Prevents duplicate processing

## Tech Stack

- Python
- Gmail API
- OpenAI API
- Pydantic
- SQLite
- Pushover

## Architecture

```mermaid
flowchart TD

A[Gmail API]
B[Fetch Latest Inbox Emails]
C[OpenAI + Pydantic<br/>EmailDecision Schema]
D{Decision}
E[Send Pushover Notification]
F[Save Task in SQLite<br/>Status: Pending]
G[Add to Digest / Mark Completed]
H[Ignore / Mark Completed]
I[User Acknowledges in Pushover]
J[Next Script Run]
K[Check Pushover Receipt]
L[Update SQLite<br/>Status: Completed]

A --> B
B --> C
C --> D

D -->|notify| E
E --> F
F --> I
I --> J
J --> K
K --> L

D -->|digest| G
D -->|ignore| H

G --> L
H --> L
```

## Setup

Clone the repository:

```bash
git clone <repo-url>
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create a `.env` file with:

```text
OPENAI_API_KEY=...
PUSHOVER_API_TOKEN=...
PUSHOVER_USER_KEY=...
```

Configure Gmail OAuth credentials:

credentials.json

Run:

```bash
python main.py
```

## Example Use Case

The project was built to help parents avoid missing important school emails by automatically prioritizing and notifying urgent items.
