import re
import time
from dataclasses import dataclass
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from governed_analytics_mcp import config

# In production this is your identity provider's user → warehouse role mapping.
KNOWN_ROLES = {"emma": "emma", "jake": "jake", "dana": "dana", "sam": "sam"}
_ROLE_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


class IdentityError(PermissionError):
    pass


@dataclass(frozen=True)
class Asker:
    user_id: str
    role: str


def asker_for_subject(subject: str | None) -> Asker:
    role = KNOWN_ROLES.get(subject or "")
    if role is None or not _ROLE_RE.match(role):
        raise IdentityError(f"no warehouse role for subject {subject!r}")
    return Asker(user_id=subject, role=role)


def ensure_keys(keys_dir: Path = config.KEYS_DIR) -> tuple[Path, Path]:
    private_path = keys_dir / "private.pem"
    public_path = keys_dir / "public.pem"
    if not private_path.exists():
        keys_dir.mkdir(parents=True, exist_ok=True)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_path.write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        private_path.chmod(0o600)
        public_path.write_bytes(
            key.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
    return private_path, public_path


def public_key(keys_dir: Path = config.KEYS_DIR) -> str:
    return ensure_keys(keys_dir)[1].read_text()


def mint_token(
    subject: str,
    expires_in: int = 8 * 3600,
    audience: str = config.TOKEN_AUDIENCE,
    keys_dir: Path = config.KEYS_DIR,
) -> str:
    private_path, _ = ensure_keys(keys_dir)
    now = int(time.time())
    claims = {
        "sub": subject,
        "iss": config.TOKEN_ISSUER,
        "aud": audience,
        "iat": now,
        "exp": now + expires_in,
        "scope": "analytics:read",
    }
    return jwt.encode(claims, private_path.read_text(), algorithm="RS256")


def verify_token(token: str, keys_dir: Path = config.KEYS_DIR) -> Asker:
    try:
        claims = jwt.decode(
            token,
            public_key(keys_dir),
            algorithms=["RS256"],
            audience=config.TOKEN_AUDIENCE,
            issuer=config.TOKEN_ISSUER,
        )
    except jwt.PyJWTError as exc:
        raise IdentityError(f"invalid token: {exc}") from None
    return asker_for_subject(claims.get("sub"))
