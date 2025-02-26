# Auth Service - Product Context

## Project Overview

**auth_service** is a production-ready FastAPI-based authentication service designed to handle user authentication and management. It uses PostgreSQL for storing user data and provides secure JWT-based authentication with comprehensive logging and monitoring capabilities.

## Project Vision

To provide a robust, secure, and scalable authentication service that can be easily integrated into various applications, offering comprehensive user management, credit system functionality, and email integration.

## Key Goals

1. Provide secure user authentication and management
2. Implement a reliable credit system for user transactions
3. Ensure comprehensive logging and monitoring
4. Support email integration for notifications and password resets
5. Maintain high performance and scalability
6. Follow best practices for security and data protection

## Technical Constraints

1. Python 3.11 or higher required
2. PostgreSQL database dependency
3. Poetry for dependency management
4. Environment-based configuration through .env files

## Core Features

1. **User Authentication**
   - Secure user registration and login
   - JWT-based authentication with configurable expiration
   - Password reset functionality with email integration
   - bcrypt password hashing

2. **Credit System**
   - Secure credit balance management
   - Transaction history tracking
   - Credit addition and usage operations
   - Atomic transactions for data consistency
   - Detailed audit logging
   - Protection against negative balances
   - Transaction reference tracking

3. **Advanced Logging**
   - Structured JSON logging
   - Logstash integration for centralized logging
   - Detailed error tracking with stack traces
   - Environment-specific logging configurations
   - TCP-based log shipping

4. **Email Integration**
   - SMTP support with SSL/TLS
   - Customizable email templates
   - Password reset email functionality
   - Configurable email settings

5. **Database**
   - Async PostgreSQL support with SQLAlchemy
   - Database migrations using Alembic
   - Connection pooling
   - Test database configuration

6. **Security**
   - CORS middleware with configurable origins
   - Request validation
   - Structured error handling
   - Environment-based configurations

## Project Structure

The project follows a modular structure with clear separation of concerns:

- **Core Components**: JWT handling, configuration, database connections, email service
- **Models**: SQLAlchemy models for users, credits, and transactions
- **Routers**: API endpoints for authentication and credit operations
- **Services**: Business logic for user management and credit operations
- **Schemas**: Pydantic models for request/response validation
- **Templates**: Email templates for various notifications

## Memory Bank Files

This Memory Bank contains the following core files:

1. **productContext.md** (this file): Project overview, vision, goals, and constraints
2. **activeContext.md**: Current session state and goals
3. **progress.md**: Work completed and next steps
4. **decisionLog.md**: Key architectural decisions and their rationale

Additional files may be created as needed to document specific aspects of the project.