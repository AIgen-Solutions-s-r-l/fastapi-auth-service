# Authentication Service Tools

This directory contains utility scripts for interacting with the authentication service.

## Installation

Install the required dependencies:

```bash
pip install -r requirements.txt
```

## Available Tools

### 1. Register Email

Register a new user and verify the email using the database token.

```bash
./register_mail.py --email new.user@example.com --password your_password --delay 3
```

**Options:**
- `--email`: Email address for registration (required)
- `--password`: Password for the account (required)
- `--delay`: Delay in seconds after registration (default: 2)
- `--pg-host`: PostgreSQL host (default: 172.17.0.1)
- `--pg-port`: PostgreSQL port (default: 5432)
- `--pg-user`: PostgreSQL username (default: testuser)
- `--pg-password`: PostgreSQL password
- `--pg-db`: PostgreSQL database name (default: main_db)

### 2. Get Authentication Token

Authenticate and retrieve a JWT bearer token.

```bash
./get_token.py --email user@example.com --password your_password
```

**Options:**
- `--email`: Email address for login (required)
- `--password`: Password for login (required)
- `--show-full`: Show the full response details

### 3. Test Email Sending

Test the email sending functionality.

```bash
./test_email.py --email test@example.com
```

## Examples

### Register a new user and verify email:

```bash
./register_mail.py --email test123@example.com --password securepass123
```

### Login and get a token:

```bash
./get_token.py --email test123@example.com --password securepass123
```

### Use the token with curl:

```bash
curl -H 'Authorization: Bearer YOUR_TOKEN_HERE' http://localhost:8001/auth/me