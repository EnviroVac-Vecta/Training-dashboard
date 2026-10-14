"""Build the training dashboard site from the HSI Training Summary file.

1. Gets the Training Summary Excel file from SharePoint through the
   Power Automate flow at TRAINING_SUMMARY_URL (the flow answers with the
   file itself). For a local test, pass a file path instead:
       python build.py "Training Summary.xlsx"
2. Turns the rows into the dashboard's data format.
3. If the DASHBOARD_PASSCODE secret is set, locks the data with it (AES-GCM)
   so the page asks for the passcode. Without it, the data is published open.
4. Writes the finished site to site/.
"""
import io
import os
import sys
import json
import base64
import shutil
from datetime import datetime, date, timezone

import requests
from openpyxl import load_workbook
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "site")
ITERATIONS = 200_000
NO_EXPIRATION_YEAR = 2050  # expire dates this far out mean "doesn't expire"

# Dashboard column -> header names the export might use (lowercase, no spaces/punctuation).
COLUMNS = {
    "Employee ID": ["employeeid", "empid", "employeenumber", "eeid", "id"],
    "Name": ["name", "employeename", "fullname", "membername"],
    "Role": ["role", "jobtitle", "title", "position"],
    "Location": ["location", "team", "teams", "site"],
    "Course Name": ["coursename", "course", "training", "trainingname", "coursetitle"],
    "Score": ["score"],
    "Date Assigned": ["dateassigned", "assigned", "assigneddate", "assignmentdate"],
    "Date Completed": ["datecompleted", "completed", "completeddate", "completiondate"],
    "Date Expire": ["dateexpire", "expire", "expires", "expiredate", "expirationdate", "dateexpires"],
    "Status": ["status", "coursestatus", "completionstatus"],
}
REQUIRED = ["Name", "Course Name", "Date Expire", "Status"]


def norm(text):
    return "".join(ch for ch in str(text or "").lower() if ch.isalnum())


def get_file():
    if len(sys.argv) > 1:
        with open(sys.argv[1], "rb") as f:
            return f.read()
    secrets = json.loads(os.environ.get("ALL_SECRETS") or "{}")
    url = secrets.get("TRAINING_SUMMARY_URL") or os.environ.get("TRAINING_SUMMARY_URL")
    if not url:
        raise SystemExit("Missing GitHub secret: TRAINING_SUMMARY_URL")
    print("Getting the Training Summary file from SharePoint...")
    res = requests.post(url, json={}, timeout=180)
    if res.status_code != 200:
        raise SystemExit(f"The SharePoint flow returned {res.status_code}: {res.text[:300]}")
    body = res.content
    if not body.startswith(b"PK"):
        # The flow may have answered with JSON holding the file as base64.
        try:
            j = res.json()
            b = j.get("$content") or j.get("fileContent") or j.get("body", {}).get("$content")
            body = base64.b64decode(b)
        except Exception:
            raise SystemExit("The SharePoint flow didn't send back an Excel file. "
                             f"First bytes: {res.content[:120]!r}")
    print(f"Got {len(body):,} bytes.")
    return body


def iso(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        d = value.date()
    elif isinstance(value, date):
        d = value
    else:
        text = str(value).strip()
        d = None
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y %I:%M %p"):
            try:
                d = datetime.strptime(text, fmt).date()
                break
            except ValueError:
                continue
        if d is None:
            return None
    return d.isoformat()


def read_rows(xlsx_bytes):
    wb = load_workbook(io.BytesIO(xlsx_bytes), read_only=True, data_only=True)
    best = None
    for ws in wb.worksheets:
        rows = ws.iter_rows(values_only=True)
        for i, row in enumerate(rows):
            if i > 15:
                break
            headers = [norm(c) for c in row]
            found = {}
            for col, names in COLUMNS.items():
                # Exact column name first, then the other names in order of preference.
                for want in [norm(col)] + names:
                    if want in headers:
                        found[col] = headers.index(want)
                        break
            if all(c in found for c in REQUIRED):
                best = (ws, i, found, [str(c or "") for c in row])
                break
        if best:
            break
    if not best:
        sheet_info = []
        for ws in wb.worksheets:
            first = next(ws.iter_rows(values_only=True, max_row=1), ())
            sheet_info.append(f"{ws.title}: {[c for c in first if c]}")
        raise SystemExit("Couldn't find the header row (need Name, Course Name, Date Expire, Status). "
                         "Sheets and first rows: " + " | ".join(sheet_info))

    ws, header_row, found, header_text = best
    print(f"Using sheet '{ws.title}', headers on row {header_row + 1}: "
          + ", ".join(f"{c} <- '{header_text[i]}'" for c, i in found.items()))
    cols = list(COLUMNS)
    out = []
    for row in ws.iter_rows(min_row=header_row + 2, values_only=True):
        if not any(v not in (None, "") for v in row):
            continue
        rec = []
        for col in cols:
            idx = found.get(col)
            v = row[idx] if idx is not None and idx < len(row) else None
            if col.startswith("Date"):
                v = iso(v)
                if col == "Date Expire" and v and int(v[:4]) >= NO_EXPIRATION_YEAR:
                    v = None
            elif isinstance(v, str):
                v = v.strip() or None
            elif isinstance(v, float) and v.is_integer():
                v = int(v)
            rec.append(v)
        if not rec[cols.index("Name")]:
            continue
        out.append(rec)
    return cols, out


def encrypt(obj, passcode):
    salt, iv = os.urandom(16), os.urandom(12)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS).derive(passcode.encode())
    data = AESGCM(key).encrypt(iv, json.dumps(obj, separators=(",", ":")).encode(), None)
    b = lambda x: base64.b64encode(x).decode()
    return {"v": 1, "iter": ITERATIONS, "salt": b(salt), "iv": b(iv), "data": b(data)}


def main():
    secrets = json.loads(os.environ.get("ALL_SECRETS") or "{}")
    passcode = secrets.get("DASHBOARD_PASSCODE") or os.environ.get("DASHBOARD_PASSCODE")

    cols, rows = read_rows(get_file())
    if not rows:
        raise SystemExit("The Training Summary file had no data rows.")
    people = len({(r[0] or r[1]) for r in rows})
    print(f"{len(rows):,} training rows for {people:,} employees.")

    data = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "cols": cols, "rows": rows}
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT)
    shutil.copy(os.path.join(HERE, "index.html"), os.path.join(OUT, "index.html"))
    if passcode:
        with open(os.path.join(OUT, "data.enc.json"), "w") as f:
            json.dump(encrypt(data, passcode), f)
        print("Data locked with DASHBOARD_PASSCODE.")
    else:
        with open(os.path.join(OUT, "data.json"), "w") as f:
            json.dump(data, f, separators=(",", ":"))
        print("No DASHBOARD_PASSCODE secret: publishing without a passcode.")
    with open(os.path.join(OUT, "robots.txt"), "w") as f:
        f.write("User-agent: *\nDisallow: /\n")
    print(f"::notice title=Training dashboard::{len(rows):,} rows, {people:,} employees")


if __name__ == "__main__":
    main()
