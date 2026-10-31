from app.core.secrets import seal, unseal


def test_outbox_credentials_are_encrypted_and_authenticated():
    token = "single-use-verification-credential"
    encoded = seal(token)
    assert token not in encoded
    assert unseal(encoded) == token
    assert seal(token) != encoded
