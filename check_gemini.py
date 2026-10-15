"""Check your Gemini key: lists the models it can use and tests each with a tiny request.
Run:  python check_gemini.py        (reads .streamlit/secrets.toml; never prints the key)
"""
import json, os, sys, tomllib, urllib.error, urllib.request

BASE = "https://generativelanguage.googleapis.com/v1beta"


def key() -> str:
    k = os.environ.get("GEMINI_API_KEY")
    if k:
        return k
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".streamlit", "secrets.toml")
    try:
        with open(path, "rb") as f:
            return tomllib.load(f).get("GEMINI_API_KEY", "")
    except FileNotFoundError:
        return ""


def call(url, k, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                                 headers={"x-goog-api-key": k, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            msg = json.load(e).get("error", {}).get("message", "")
        except Exception:
            msg = ""
        return e.code, " ".join(msg.replace(k, "***").split())[:140]
    except Exception as e:
        return 0, type(e).__name__


def main():
    k = key()
    if not k:
        sys.exit("No GEMINI_API_KEY found in .streamlit\\secrets.toml. Check the file is saved and has the line GEMINI_API_KEY = \"...\"")
    print(f"Key found ({len(k)} characters, starts with {k[:3]}...)\n")
    code, data = call(f"{BASE}/models?pageSize=200", k)
    if code != 200:
        sys.exit(f"Could not list models: HTTP {code} {data}")
    names = [m["name"].split("/")[1] for m in data.get("models", [])
             if "generateContent" in m.get("supportedGenerationMethods", []) and "flash" in m["name"]
             and not any(x in m["name"] for x in ("image", "tts", "live", "audio", "embedding", "robotics"))]
    print(f"{len(names)} flash models available to your key. Testing each:\n")
    body = {"contents": [{"parts": [{"text": "Reply with the single word OK"}]}]}
    for n in names[:12]:
        code, data = call(f"{BASE}/models/{n}:generateContent", k, body)
        print(f"  {'WORKS' if code == 200 else 'HTTP ' + str(code):9} {n}" + ("" if code == 200 else f"   {data}"))
    print("\nPut a model that WORKS in .streamlit\\secrets.toml as:  GEMINI_MODEL = \"name-here\"")


main()
