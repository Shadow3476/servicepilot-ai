from servicepilot.auth import (
    LoginLimiter,
    check_admin_password,
    hash_password,
    session_expired,
    uses_legacy_password,
    verify_password,
)


def test_hash_and_verify_roundtrip():
    h = hash_password("s3cret-pass", iterations=1000)
    assert h.startswith("pbkdf2_sha256$1000$")
    assert "s3cret-pass" not in h
    assert verify_password("s3cret-pass", h)
    assert not verify_password("wrong", h)


def test_hashes_are_salted():
    assert hash_password("same", 1000) != hash_password("same", 1000)


def test_malformed_hash_fails_closed():
    assert not verify_password("x", "garbage")
    assert not verify_password("x", "md5$1$aa$bb")


def test_prefers_hash_over_legacy():
    h = hash_password("new", 1000)
    secrets = {"password_hash": h, "password": "old"}
    assert check_admin_password("new", secrets)
    assert not check_admin_password("old", secrets)


def test_legacy_plaintext_still_works_and_is_flagged():
    secrets = {"password": "old"}
    assert check_admin_password("old", secrets)
    assert not check_admin_password("nope", secrets)
    assert uses_legacy_password(secrets)


def test_no_password_configured_denies_everyone():
    assert not check_admin_password("", {})
    assert not check_admin_password("anything", {})


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_lockout_after_repeated_failures_then_expires():
    clock = Clock()
    lim = LoginLimiter(max_failures=3, window=60, lockout=120, clock=clock)
    for _ in range(2):
        lim.record_failure()
    assert lim.seconds_locked() == 0
    lim.record_failure()
    assert lim.seconds_locked() > 0
    clock.t = 121
    assert lim.seconds_locked() == 0


def test_success_resets_failures():
    lim = LoginLimiter(max_failures=3, clock=Clock())
    lim.record_failure()
    lim.record_failure()
    lim.record_success()
    lim.record_failure()
    assert lim.seconds_locked() == 0


def test_session_expiry():
    assert session_expired(None, 100)
    assert not session_expired(100, 200, timeout=1800)
    assert session_expired(100, 2000, timeout=1800)
