import jwt
import pytest

from governed_analytics_mcp import config
from governed_analytics_mcp.identity import (
    IdentityError,
    asker_for_subject,
    ensure_keys,
    mint_token,
    verify_token,
)


@pytest.fixture
def keys(tmp_path):
    ensure_keys(tmp_path)
    return tmp_path


def test_round_trip(keys):
    asker = verify_token(mint_token("emma", keys_dir=keys), keys_dir=keys)
    assert (asker.user_id, asker.role) == ("emma", "emma")


def test_token_for_another_audience_is_rejected(keys):
    token = mint_token("emma", audience="warehouse", keys_dir=keys)
    with pytest.raises(IdentityError, match="(?i)audience"):
        verify_token(token, keys_dir=keys)


def test_expired_token_is_rejected(keys):
    with pytest.raises(IdentityError, match="expired"):
        verify_token(mint_token("emma", expires_in=-10, keys_dir=keys), keys_dir=keys)


def test_token_signed_by_someone_else_is_rejected(keys, tmp_path_factory):
    other = tmp_path_factory.mktemp("other")
    with pytest.raises(IdentityError, match="(?i)signature"):
        verify_token(mint_token("jake", keys_dir=other), keys_dir=keys)


def test_unknown_subject_has_no_role(keys):
    token = jwt.encode(
        {
            "sub": "transformer",
            "aud": config.TOKEN_AUDIENCE,
            "iss": config.TOKEN_ISSUER,
        },
        (keys / "private.pem").read_text(),
        algorithm="RS256",
    )
    with pytest.raises(IdentityError, match="no warehouse role"):
        verify_token(token, keys_dir=keys)


@pytest.mark.parametrize("subject", [None, "", "postgres", "emma; RESET ROLE"])
def test_only_known_subjects_map_to_roles(subject):
    with pytest.raises(IdentityError):
        asker_for_subject(subject)
