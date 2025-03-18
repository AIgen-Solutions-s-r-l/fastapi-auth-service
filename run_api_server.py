"""
Script to run the API server for testing the Stripe integration.

This runs the FastAPI application with uvicorn for development purposes.
"""

import uvicorn

if __name__ == "__main__":
    # Run the FastAPI application with uvicorn
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=9000,
        reload=True
    )