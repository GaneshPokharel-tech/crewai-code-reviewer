from pathlib import Path

USERS = {
    "admin": {
        "password": "admin123",
        "role": "admin",
    },
    "ganesh": {
        "password": "password123",
        "role": "user",
    },
}


def login(username: str, password: str) -> bool:
    user = USERS.get(username)

    if not user:
        return False

    return user["password"] == password


def calculate_discount(price: float, discount_percent: float) -> float:
    discount = price * discount_percent / 100
    return price - discount


def divide_bill(total: float, people: int) -> float:
    return total / people


def read_user_file(filename: str) -> str:
    file_path = Path("user_files") / filename

    return file_path.read_text()


def get_user_role(username: str) -> str:
    return USERS[username]["role"]
