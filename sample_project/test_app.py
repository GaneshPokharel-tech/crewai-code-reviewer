from app import calculate_discount, login


def test_valid_login():
    assert login("admin", "admin123") is True


def test_invalid_login():
    assert login("admin", "wrong-password") is False


def test_discount():
    assert calculate_discount(100, 10) == 90
