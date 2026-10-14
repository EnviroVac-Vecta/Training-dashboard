# EnviroVac Training Dashboard

A web page managers open to view, sort and filter everyone's HSI training status.
Each morning (~6:45 AM Central) the **Training Dashboard** workflow gets the Training Summary
file from SharePoint, rebuilds the dashboard, and publishes it to GitHub Pages at
**https://envirovac-vecta.github.io/training-dashboard/**.

Anyone with the link can open it. Each person's filters are their own.
Optional passcode: add the `DASHBOARD_PASSCODE` secret and run the workflow, and the page will ask
for it (people enter it once; their browser remembers it). Delete the secret to turn it off again.
No training data is stored in this repo; it only goes into the published site.

| File | What it does |
|---|---|
| `index.html` | the dashboard page |
| `build.py` | Training Summary file → locked dashboard data |
| `.github/workflows/training_dashboard.yml` | the daily run |

## Setup
1. **Power Automate flow "Training Summary - Send file"**
   - Trigger: *When an HTTP request is received* (who can trigger: Anyone).
   - SharePoint *Get file content using path* → the site and the Training Summary file.
   - *Response* → Status code `200`, Body = *File Content* from the step above.
   - Save, then copy the trigger's HTTP URL.
2. **Secrets** (Settings → Secrets and variables → Actions → New repository secret):
   | Secret | What |
   |---|---|
   | `TRAINING_SUMMARY_URL` | the flow's HTTP URL from step 1 |
   | `DASHBOARD_PASSCODE` | optional - only if you want a passcode (use a phrase, not a short number) |
3. **Pages**: Settings → Pages → Build and deployment → Source: **GitHub Actions**.
4. Actions → **Training Dashboard** → **Run workflow**.

## Notes
- Passcode on/off: add or delete `DASHBOARD_PASSCODE`, then run the workflow.
- Change the time: edit the `cron` line in the workflow (UTC; Central = UTC−5 summer, UTC−6 winter).
- The Training Summary file must keep these column headers: Employee ID, Name, Role, Location,
  Course Name, Score, Date Assigned, Date Completed, Date Expire, Status.
- If a run fails, open it in Actions; the error is shown on the run's summary page.
