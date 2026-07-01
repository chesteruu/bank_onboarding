from uuid import uuid4

from onboarding.services.resume_tokens_crypto import hash_token, mint_token, new_salt


def test_token_is_deterministic_for_same_inputs():
    app_id = uuid4()
    salt = new_salt()
    assert mint_token("secret", app_id, salt) == mint_token("secret", app_id, salt)


def test_token_depends_on_secret():
    app_id = uuid4()
    salt = new_salt()
    assert mint_token("secret-a", app_id, salt) != mint_token("secret-b", app_id, salt)


def test_token_depends_on_salt_and_application():
    salt_a, salt_b = new_salt(), new_salt()
    app_id = uuid4()
    assert mint_token("secret", app_id, salt_a) != mint_token("secret", app_id, salt_b)
    assert mint_token("secret", uuid4(), salt_a) != mint_token("secret", uuid4(), salt_a)


def test_stored_hash_is_not_the_raw_token():
    token = mint_token("secret", uuid4(), new_salt())
    stored = hash_token(token)
    assert stored != token
    assert len(stored) == 64  # sha256 hex
    # The hash is not reversible; the raw token cannot be derived from storage.
    assert hash_token(token) == stored
