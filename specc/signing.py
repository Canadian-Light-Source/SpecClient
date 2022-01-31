import base64
import string
import os

def generate_api_key() -> str:
    choices = string.ascii_letters + string.digits
    altchars = ''.join([choices[ord(os.urandom(1)) % 62] for _ in range(2)]).encode("utf-8")
    api_key = base64.b64encode(os.urandom(24), altchars=altchars).decode("utf-8")
    os.putenv("API_KEY", api_key)
    return api_key