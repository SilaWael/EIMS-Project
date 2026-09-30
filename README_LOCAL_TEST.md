# EIMS Local Test Build v3

This build restores the Master Registry page while keeping the new Dashboard and Progress & Reports page.

## Main changes
- Dashboard remains the main all-in-one page with KPIs, universal search, filters, full results, and engineering inspector.
- Master Registry is fully populated from `eims.db` and supports universal search across record fields plus date/category/sub-category/status filters.
- Progress & Reports remains available as a separate reporting workspace.
- `run_app.bat` uses the Windows Python launcher (`py -3`) to avoid Microsoft Store `python` alias issues.

## Run
Double-click `EIMS.vbs` for the normal daily use: it starts the server with **no black console window**, waits until the app answers, and opens the browser at http://localhost:8521. Nothing fails silently - any problem is reported in a message box.

Double-click `run_app.bat` instead when you want to see the console output (dependency check, error messages, live server log).

`EIMS.vbs` uses the Windows Python launcher (`py -3`) to avoid Microsoft Store `python` alias issues, exactly like `run_app.bat`. Clicking it twice is safe: if EIMS is already running on port 8521 it only reopens the browser. To stop EIMS, close the browser tab and end the `python.exe` process running `app.py` in Task Manager.

The included `eims.db` is a copy for testing only. No GitHub files were changed by this build.
