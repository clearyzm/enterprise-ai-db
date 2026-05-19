"""Password hashing utilities using Argon2id.

Uses argon2-cffi with security parameters:
- time_cost=3 (iterations)
- memory_cost=65536 (64 MB)
- parallelism=4 (threads)

These parameters provide strong security while maintaining reasonable performance.
"""
from argon2 import PasswordHasher, Type
from argon2.exceptions import VerifyMismatchError, InvalidHashError, VerificationError


# Initialize Argon2id hasher with specified parameters
# Reference: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
_hasher = PasswordHasher(
    time_cost=3,  # Number of iterations
    memory_cost=65536,  # 64 MB memory usage
    parallelism=4,  # Number of parallel threads
    hash_len=32,  # Output hash length in bytes
    salt_len=16,  # Salt length in bytes
    encoding="utf-8",
    type=Type.ID,  # Argon2id (hybrid of Argon2i and Argon2d)
)


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id.
    
    Args:
        password: Plaintext password to hash
    
    Returns:
        Argon2id hash string (includes algorithm, parameters, salt, and hash)
        Format: $argon2id$v=19$m=65536,t=3,p=4$<salt>$<hash>
    
    Example:
        >>> hash_password("demo123456")
        '$argon2id$v=19$m=65536,t=3,p=4$...$...'
    """
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against an Argon2id hash.
    
    Args:
        password: Plaintext password to verify
        password_hash: Argon2id hash string from database
    
    Returns:
        True if password matches, False otherwise
    
    Example:
        >>> hash_str = hash_password("demo123456")
        >>> verify_password("demo123456", hash_str)
        True
        >>> verify_password("wrong", hash_str)
        False
    """
    try:
        _hasher.verify(password_hash, password)
        return True
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        # VerifyMismatchError: Password doesn't match
        # InvalidHashError: Malformed hash string
        # VerificationError: Other verification errors
        return False


def needs_rehash(password_hash: str) -> bool:
    """Check if a password hash needs to be rehashed with current parameters.
    
    Use this after successful login to upgrade old hashes to current parameters.
    
    Args:
        password_hash: Argon2id hash string from database
    
    Returns:
        True if hash should be regenerated with current parameters
    
    Example:
        >>> if verify_password(password, user.password_hash):
        ...     if needs_rehash(user.password_hash):
        ...         user.password_hash = hash_password(password)
        ...         await session.commit()
    """
    try:
        return _hasher.check_needs_rehash(password_hash)
    except (InvalidHashError, ValueError):
        # If hash is invalid, it definitely needs rehashing
        return True
