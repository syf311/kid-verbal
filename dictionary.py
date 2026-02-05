import requests
from typing import Optional


def fetch_definition(word: str) -> Optional[dict]:
    """
    Fetch word definition from Free Dictionary API.
    Returns dict with 'definition' and 'example' or None if not found.
    """
    try:
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
        response = requests.get(url, timeout=5)

        if response.status_code != 200:
            return None

        data = response.json()
        if not data or not isinstance(data, list):
            return None

        # Get first definition
        meanings = data[0].get("meanings", [])
        if not meanings:
            return None

        definitions = meanings[0].get("definitions", [])
        if not definitions:
            return None

        first_def = definitions[0]
        return {
            "definition": first_def.get("definition", ""),
            "example": first_def.get("example", "")
        }
    except Exception:
        return None


if __name__ == "__main__":
    # Quick test
    result = fetch_definition("happy")
    print(result)
