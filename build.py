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


TAPPI_COLUMNS = {"first": ["firstname"], "last": ["lastname"], "id": ["studentid"], "course": ["description", "course", "coursename"],
                 "date": ["classdate", "datecompleted"], "exp": ["expirationdate", "expiredate"], "grade": ["grade", "result"]}


def fetch_xlsx(secret_name, label):
    """Post to a Power Automate flow that answers with an Excel file. None if the secret isn't set."""
    secrets = json.loads(os.environ.get("ALL_SECRETS") or "{}")
    url = secrets.get(secret_name) or os.environ.get(secret_name)
    if not url:
        return None
    res = requests.post(url, json={}, timeout=180)
    body = res.content
    if res.status_code == 200 and not body.startswith(b"PK"):
        try:
            j = res.json()
            body = base64.b64decode(j.get("$content") or j.get("fileContent") or j.get("body", {}).get("$content"))
        except Exception:
            pass
    if res.status_code != 200 or not body.startswith(b"PK"):
        print(f"::warning title={label}::The {label} flow didn't send back an Excel file (status {res.status_code}); skipping it.")
        return None
    return body


def read_tappi(xlsx_bytes):
    """TAPPISAFE Student Attendance export -> compact rows for the Plant Sites tab."""
    wb = load_workbook(io.BytesIO(xlsx_bytes), read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    for h, row in enumerate(rows[:15]):
        headers = [norm(c) for c in row]
        found = {k: next((headers.index(n) for n in names if n in headers), None) for k, names in TAPPI_COLUMNS.items()}
        if found["course"] is not None and found["last"] is not None:
            break
    else:
        print("::warning title=TAPPI::Couldn't find the header row in the TAPPI file; skipping the Plant Sites tab.")
        return None
    cols = list(TAPPI_COLUMNS)
    out = []
    for r in rows[h + 1:]:
        g = lambda k: r[found[k]] if found[k] is not None and found[k] < len(r) else None
        if not g("course") or not g("last"):
            continue
        out.append([str(g("first") or "").strip(), str(g("last") or "").strip(), str(g("id") or "").strip(),
                    str(g("course")).strip(), iso(g("date")), iso(g("exp")), str(g("grade") or "").strip()])
    print(f"TAPPI: {len(out):,} course records.")
    return {"cols": cols, "rows": out}


def read_refresher(xlsx_bytes):
    """HSI Training Requirement Status > By Team/Member - All -> compact rows for the Refresher Training view."""
    wb = load_workbook(io.BytesIO(xlsx_bytes), read_only=True, data_only=True)
    rows = list(wb.worksheets[0].iter_rows(values_only=True))
    h = next((i for i, r in enumerate(rows[:15]) if r and "Requirement" in [str(v or "").strip() for v in r]
              and "First Name" in [str(v or "").strip() for v in r]), None)
    if h is None:
        print("::warning title=Refresher::Couldn't find the header row in the refresher file; skipping it.")
        return None
    hdr = [str(v or "").strip() for v in rows[h]]
    col = lambda n: hdr.index(n) if n in hdr else None
    c = {k: col(n) for k, n in (("first", "First Name"), ("last", "Last Name"), ("team", "Teams"), ("req", "Requirement"),
                                 ("status", "Compliance Status"), ("last_done", "Last Completion Date"),
                                 ("window", "Start Date for Next Due"), ("due", "Due Date"))}
    reqs, out = [], []
    for r in rows[h + 1:]:
        g = lambda k: r[c[k]] if c[k] is not None and c[k] < len(r) else None
        if not g("req") or not g("last"):
            continue
        last, emp_id = str(g("last")).strip(), ""
        if "," in last:  # HSI puts the login ID after the last name: "Ferguson,3LDUWVKMI"
            last, emp_id = [x.strip() for x in last.split(",", 1)]
        req = str(g("req")).strip()
        if req not in reqs:
            reqs.append(req)
        out.append([emp_id, (str(g("first") or "").strip() + " " + last).strip(), str(g("team") or "").strip(),
                    reqs.index(req), str(g("status") or "").strip(), iso(g("last_done")), iso(g("window")), iso(g("due"))])
    print(f"Refresher: {len(out):,} requirement rows, {len(reqs)} requirements.")
    return {"reqs": reqs, "rows": out}


def main():
    secrets = json.loads(os.environ.get("ALL_SECRETS") or "{}")
    passcode = secrets.get("DASHBOARD_PASSCODE") or os.environ.get("DASHBOARD_PASSCODE")

    cols, rows = read_rows(get_file())
    if not rows:
        raise SystemExit("The Training Summary file had no data rows.")
    people = len({(r[0] or r[1]) for r in rows})
    print(f"{len(rows):,} training rows for {people:,} employees.")

    data = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "cols": cols, "rows": rows}
    # Plant Sites tab: the TAPPISAFE attendance file (Tappi Raw Data), when its flow is set up.
    tappi_path = os.environ.get("TAPPI_FILE")
    tappi_bytes = open(tappi_path, "rb").read() if tappi_path else fetch_xlsx("TAPPI_URL", "TAPPI")
    tappi = read_tappi(tappi_bytes) if tappi_bytes else None
    if tappi:
        data["tappi"] = tappi
    # Refresher Training view: HSI Training Requirement Status (HSI Refresher Training.xlsx).
    ref_path = os.environ.get("REFRESHER_FILE")
    ref_bytes = open(ref_path, "rb").read() if ref_path else fetch_xlsx("REFRESHER_URL", "Refresher")
    refresher = read_refresher(ref_bytes) if ref_bytes else None
    if refresher:
        data["refresher"] = refresher
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT)
    for name in ("index.html", "plants.js"):
        shutil.copy(os.path.join(HERE, name), os.path.join(OUT, name))
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
    print(f"::notice title=Training dashboard::{len(rows):,} rows, {people:,} employees"
          + (f", {len(tappi['rows']):,} TAPPI records" if tappi else ", no TAPPI file yet (plant-site readiness off; add the TAPPI_URL secret)")
          + (f", {len(refresher['rows']):,} refresher rows" if refresher else ", no refresher file yet (add the REFRESHER_URL secret)"))


if __name__ == "__main__":
    main()
