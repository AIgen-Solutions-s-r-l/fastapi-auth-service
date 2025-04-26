# app/core/security.py
import bcrypt
from datetime import datetime, timedelta, timezone
from jose import jwt

from app.core.config import settings
from app.log.logging import logger # Added import


def get_password_hash(password: str) -> str:
    """
    Generate password hash using bcrypt.

    Args:
        password: Plain text password

    Returns:
        Hashed password as string
    """
    # Generate salt and hash password
    salt = bcrypt.gensalt()
    password_bytes = password.encode('utf-8')
    return bcrypt.hashpw(password_bytes, salt).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify password against hash using bcrypt.

    Args:
        plain_password: Password to verify
        hashed_password: Hash to verify against

    Returns:
        True if password matches hash
    """
    # Added logging to check hashed_password type and value
    logger.debug(
        f"Verifying password. Hashed password type: {type(hashed_password)}, value: {hashed_password}"
    )

    password_bytes = plain_password.encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hashed_bytes)


def create_access_token(data: dict, expires_delta: timedelta = None) -> str:
    """
    Create JWT access token.

    Args:
        data: Data to encode in token
        expires_delta: Optional expiration time

    Returns:
        JWT token string
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta  # Updated line
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)  # Updated line
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)

        # Added logging to check encoded_jwt type and value
    logger.info(
        f"Encoded JWT token type: {type(encoded_jwt)}, value: {encoded_jwt}"
    )
    # Log the expiration time
    logger.info(
        f"Token expiration time: {expire.isoformat()}"
    )
    # Log the data being encoded
    logger.info(
        f"Data being encoded in token: {to_encode}"
    )
    # Log the algorithm used
    logger.info(
        f"JWT algorithm used: {settings.algorithm}"
    )
    # Log the secret key length
    logger.info(
        f"Secret key length: {len(settings.secret_key)}"
    )
    # Log the current UTC time
    logger.info(
        f"Current UTC time: {datetime.now(timezone.utc).isoformat()}"
    )
    # Log the expiration time in UTC
    logger.info(
        f"Token expiration time in UTC: {expire.isoformat()}"
    )
    # Log the current time in UTC
    logger.info(
        f"Current time in UTC: {datetime.now(timezone.utc).isoformat()}"
    )

    return encoded_jwt


def verify_jwt_token(token: str) -> dict:
    """
    Verify a JWT, with manual leeway handling for exp.

    Raises:
      ExpiredSignatureError if token is expired (beyond skew)
      JWTError for any other invalidity
    """
    # 1) Preview for logs
    token_preview = token[:50] + "..." if len(token) > 50 else token
    logger.debug("verify_jwt_token – received", token_preview=token_preview)

    # 2) Decode without checks to see the raw payload
    try:
        unverified = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
            options={"verify_signature": False, "verify_exp": False},
        )
        logger.debug("verify_jwt_token – unverified payload", payload=unverified)
    except Exception as e:
        logger.error("verify_jwt_token – cannot decode unverified", error=str(e))
        raise Exception(f"Cannot parse token: {e}")

    # 3) Manual exp check with 30 s skew
    now_ts = int(datetime.now(timezone.utc).timestamp())
    exp_ts = unverified.get("exp")
    if exp_ts is None:
        logger.error("verify_jwt_token – missing exp claim", payload=unverified)
        raise Exception("Missing exp claim")
    if now_ts > exp_ts + 30:
        logger.error(
            "verify_jwt_token – token expired",
            now_ts=now_ts,
            exp_ts=exp_ts,
            skew_s=30,
            token_preview=token_preview
        )
        raise Exception("Token has expired")

    # 4) Finally, verify the signature only
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
            options={"verify_signature": True, "verify_exp": False},
        )
        logger.debug("verify_jwt_token – signature OK", payload=payload)
        return payload

    except Exception as e:
        logger.error(
            "verify_jwt_token – signature invalid",
            error=str(e),
            token_preview=token_preview
        )
        raise