import random
import requests
from bs4 import BeautifulSoup

URL = "https://www.anekdot.ru/random/anekdot/"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

def get_random_joke() -> str | None:
    try:
        resp = requests.get(URL, headers=HEADERS, timeout=10)
        resp.raise_for_status()
    except Exception:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    jokes = soup.select("div.text")
    if not jokes:
        return None

    joke = random.choice(jokes).get_text(strip=True)
    return joke
