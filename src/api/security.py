"""Security utilities for API key generation and authentication."""

import secrets
import hashlib
from src.api.config import settings


def generate_api_key(prefix: str = "vm") -> str:
    """
    Generate a secure API key.

    Args:
        prefix: Prefix for the API key (default: "vm" for VoiceMesh)

    Returns:
        API key in format: prefix_random32chars

    Example:
        >>> key = generate_api_key()
        >>> print(key)
        vm_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
    """
    random_bytes = secrets.token_urlsafe(32)
    return f"{prefix}_{random_bytes}"


def hash_api_key(api_key: str) -> str:
    """
    Hash an API key for secure storage.

    Uses SHA256 hashing with salt from settings.
    This is secure for API keys and avoids bcrypt compatibility issues.

    Args:
        api_key: Plain text API key

    Returns:
        Hashed API key (hex string)

    Example:
        >>> key = "vm_abc123"
        >>> hashed = hash_api_key(key)
        >>> verify_api_key(key, hashed)  # True
    """
    # Add salt and hash with SHA256
    salted_key = f"{api_key}{settings.API_KEY_SALT}"
    return hashlib.sha256(salted_key.encode()).hexdigest()


def verify_api_key(plain_api_key: str, hashed_api_key: str) -> bool:
    """
    Verify a plain API key against its hash.

    Args:
        plain_api_key: Plain text API key
        hashed_api_key: Hashed API key from database

    Returns:
        True if API key matches, False otherwise

    Example:
        >>> key = "vm_abc123"
        >>> hashed = hash_api_key(key)
        >>> verify_api_key(key, hashed)  # True
        >>> verify_api_key("wrong_key", hashed)  # False
    """
    # Hash the provided key and compare with stored hash
    computed_hash = hash_api_key(plain_api_key)
    return computed_hash == hashed_api_key


def generate_customer_id() -> str:
    """
    Generate a unique customer ID.

    Returns:
        Customer ID in format: cust_random16chars

    Example:
        >>> customer_id = generate_customer_id()
        >>> print(customer_id)
        cust_a1b2c3d4e5f6g7h8
    """
    random_string = secrets.token_urlsafe(16)
    return f"cust_{random_string}"
