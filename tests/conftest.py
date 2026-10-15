import os, tempfile
os.environ["TRIAGE_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
