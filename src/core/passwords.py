"""Password hashing with PBKDF2 from the standard library (no extra dependency)."""
import hashlib
import secrets

ITERATIONS = 100_000


def new_salt() -> str:
    return secrets.token_hex(16)


def hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS)
    return digest.hex()


def verify(password: str, salt: str, expected_hash: str) -> bool:
    return secrets.compare_digest(hash_password(password, salt), expected_hash)


def demo_salt(username: str) -> str:
    """Stable per-user salt for seeded accounts, so reseeding can reuse a cached hash."""
    return hashlib.sha256(f"demo:{username}".encode()).hexdigest()[:32]
