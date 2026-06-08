"""
Can-One USA — Shift Report Backend
===================================
Receives shift report JSONs from the Supervisor Portal,
saves them to a P Drive folder, and serves them to the
Production Dashboard.

Setup (run once):
    pip install flask flask-cors

Run:
    python server.py

Then open:
    http://localhost:5000/portal    → Supervisor Portal
    http://localhost:5000/dashboard → Production Dashboard
"""

import os
import json
import glob
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder=".")
CORS(app)  # allows the HTML files to call the API

# ─────────────────────────────────────────────────────────────
# CONFIGURATION
# Automatically detects whether running on Render (cloud) or
# locally (P Drive). No manual changes needed.
# ─────────────────────────────────────────────────────────────

# Render sets a RENDER environment variable automatically
IS_RENDER = os.environ.get("RENDER", False)

if IS_RENDER:
    # Cloud: use Render's persistent disk
    P_DRIVE_PATH = "/data/shift-reports"
else:
    # Local: use P Drive (update this path for your machine)
    P_DRIVE_PATH = r"P:\shift-reports-data"
    # Fallback to local folder if P Drive not available:
    # P_DRIVE_PATH = os.path.join(os.path.dirname(__file__), "shift-reports")

# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def get_month_folder(date_str: str) -> str:
    """
    Returns the folder path for a given date string (YYYY-MM-DD).
    e.g. '2026-06-03' → 'P:/can-one/shift-reports/2026-06/'
    Creates the folder if it doesn't exist.
    """
    try:
        year_month = date_str[:7]  # '2026-06'
    except Exception:
        year_month = datetime.now().strftime("%Y-%m")

    folder = os.path.join(P_DRIVE_PATH, year_month)
    os.makedirs(folder, exist_ok=True)
    return folder


def build_filename(date_str: str, shift: str) -> str:
    """
    Builds a consistent filename.
    e.g. shift_report_2026-06-03_C.json
    """
    safe_date  = date_str.replace("/", "-")
    safe_shift = shift.upper().strip()
    return f"shift_report_{safe_date}_{safe_shift}.json"


# ─────────────────────────────────────────────────────────────
# ROUTES — Serve HTML files
# ─────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(".", "supervisor_portal.html")

@app.route("/portal")
def portal():
    return send_from_directory(".", "supervisor_portal.html")

@app.route("/dashboard")
def dashboard():
    return send_from_directory(".", "production_dashboard.html")


# ─────────────────────────────────────────────────────────────
# POST /submit  — Save a shift report JSON to P Drive
# ─────────────────────────────────────────────────────────────

@app.route("/submit", methods=["POST"])
def submit():
    """
    Receives a shift report JSON from the Supervisor Portal.
    Saves it to P:\can-one\shift-reports\YYYY-MM\shift_report_YYYY-MM-DD_X.json
    """
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"ok": False, "error": "No JSON body received"}), 400

        # Pull key fields
        header    = data.get("header", {})
        date_str  = header.get("date", datetime.now().strftime("%Y-%m-%d"))
        shift     = header.get("shift", "X")
        supervisor = header.get("supervisor", "Unknown")

        # Stamp the submission time
        data["meta"]["submitted_at"] = datetime.now().isoformat()

        # Build path
        folder   = get_month_folder(date_str)
        filename = build_filename(date_str, shift)
        filepath = os.path.join(folder, filename)

        # Warn if overwriting (same date + shift resubmitted)
        overwrite = os.path.exists(filepath)

        # Write JSON (pretty-printed for human readability on P Drive)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"[{datetime.now().strftime('%H:%M:%S')}] "
              f"{'OVERWRITE' if overwrite else 'NEW      '} "
              f"{filename}  ({supervisor} / {shift} Shift)")

        return jsonify({
            "ok":       True,
            "filename": filename,
            "path":     filepath,
            "overwrite": overwrite,
            "message":  f"{'Updated' if overwrite else 'Saved'}: {filename}"
        })

    except Exception as e:
        print(f"[ERROR] /submit — {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


# ─────────────────────────────────────────────────────────────
# GET /reports?month=2026-06  — Return all reports for a month
# ─────────────────────────────────────────────────────────────

@app.route("/reports", methods=["GET"])
def get_reports():
    """
    Returns all shift report JSONs for a given month.
    Query param: ?month=2026-06   (defaults to current month)
    """
    try:
        month = request.args.get("month", datetime.now().strftime("%Y-%m"))
        folder = os.path.join(P_DRIVE_PATH, month)

        if not os.path.exists(folder):
            return jsonify({"ok": True, "month": month, "reports": [], "count": 0})

        pattern = os.path.join(folder, "shift_report_*.json")
        files   = sorted(glob.glob(pattern))

        reports = []
        for filepath in files:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    reports.append(json.load(f))
            except Exception as e:
                print(f"[WARN] Could not read {filepath}: {e}")

        print(f"[{datetime.now().strftime('%H:%M:%S')}] "
              f"GET /reports?month={month} — {len(reports)} reports")

        return jsonify({
            "ok":      True,
            "month":   month,
            "reports": reports,
            "count":   len(reports)
        })

    except Exception as e:
        print(f"[ERROR] /reports — {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


# ─────────────────────────────────────────────────────────────
# GET /reports/list?month=2026-06  — List filenames only (lightweight)
# ─────────────────────────────────────────────────────────────

@app.route("/reports/list", methods=["GET"])
def list_reports():
    """
    Returns just the filenames for a month — useful for the dashboard
    to check what's been submitted without loading all data.
    """
    try:
        month  = request.args.get("month", datetime.now().strftime("%Y-%m"))
        folder = os.path.join(P_DRIVE_PATH, month)

        if not os.path.exists(folder):
            return jsonify({"ok": True, "month": month, "files": []})

        pattern = os.path.join(folder, "shift_report_*.json")
        files   = [os.path.basename(f) for f in sorted(glob.glob(pattern))]

        return jsonify({"ok": True, "month": month, "files": files})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ─────────────────────────────────────────────────────────────
# GET /reports/<date>/<shift>  — Fetch a single report for editing
# ─────────────────────────────────────────────────────────────

@app.route("/reports/<date_str>/<shift>", methods=["GET"])
def get_single_report(date_str, shift):
    """
    Returns one specific shift report so the portal can pre-fill for editing.
    Example: GET /reports/2026-06-03/C
    """
    try:
        folder   = get_month_folder(date_str)
        filename = build_filename(date_str, shift)
        filepath = os.path.join(folder, filename)

        if not os.path.exists(filepath):
            return jsonify({"ok": False, "error": "Report not found"}), 404

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        print(f"[{datetime.now().strftime('%H:%M:%S')}] LOAD     {filename}")
        return jsonify({"ok": True, "report": data, "filename": filename})

    except Exception as e:
        print(f"[ERROR] /reports/{date_str}/{shift} GET — {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


# ─────────────────────────────────────────────────────────────
# DELETE /reports/<date>/<shift>  — Remove a report (admin only)
# ─────────────────────────────────────────────────────────────

@app.route("/reports/<date_str>/<shift>", methods=["DELETE"])
def delete_report(date_str, shift):
    """
    Deletes a specific shift report.
    Example: DELETE /reports/2026-06-03/C
    """
    try:
        folder   = get_month_folder(date_str)
        filename = build_filename(date_str, shift)
        filepath = os.path.join(folder, filename)

        if not os.path.exists(filepath):
            return jsonify({"ok": False, "error": "File not found"}), 404

        os.remove(filepath)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] DELETED {filename}")
        return jsonify({"ok": True, "message": f"Deleted {filename}"})

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ─────────────────────────────────────────────────────────────
# GET /health  — Quick check that the server is running
# ─────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "ok":          True,
        "server":      "Can-One Shift Report API",
        "version":     "1.0.0",
        "environment": "Render (Cloud)" if IS_RENDER else "Local",
        "storage_path": P_DRIVE_PATH,
        "storage_exists": os.path.exists(P_DRIVE_PATH),
        "time":        datetime.now().isoformat()
    })


# ─────────────────────────────────────────────────────────────
# GET /admin/files  — Browse all stored report files
# ─────────────────────────────────────────────────────────────

@app.route("/admin/files", methods=["GET"])
def admin_files():
    """
    Lists all stored shift report files across all months.
    Open in browser: /admin/files
    """
    try:
        all_files = []
        total_size = 0

        if os.path.exists(P_DRIVE_PATH):
            # Walk all month folders
            for month_folder in sorted(os.listdir(P_DRIVE_PATH)):
                month_path = os.path.join(P_DRIVE_PATH, month_folder)
                if not os.path.isdir(month_path):
                    continue
                files_in_month = []
                for filename in sorted(os.listdir(month_path)):
                    if not filename.endswith('.json'):
                        continue
                    filepath = os.path.join(month_path, filename)
                    size = os.path.getsize(filepath)
                    modified = datetime.fromtimestamp(
                        os.path.getmtime(filepath)
                    ).isoformat()
                    total_size += size
                    files_in_month.append({
                        "filename": filename,
                        "size_kb": round(size / 1024, 1),
                        "modified": modified,
                        "url": f"/reports/{filename.replace('shift_report_','').replace('.json','').replace('_','/',1)}"
                    })
                if files_in_month:
                    all_files.append({
                        "month": month_folder,
                        "count": len(files_in_month),
                        "files": files_in_month
                    })

        return jsonify({
            "ok": True,
            "storage_path": P_DRIVE_PATH,
            "storage_exists": os.path.exists(P_DRIVE_PATH),
            "total_reports": sum(m["count"] for m in all_files),
            "total_size_kb": round(total_size / 1024, 1),
            "months": all_files
        })

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ─────────────────────────────────────────────────────────────
# START
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    print("=" * 55)
    print("  Can-One USA — Shift Report Server")
    print("=" * 55)
    print(f"  Environment  : {'Render (Cloud)' if IS_RENDER else 'Local'}")
    print(f"  Storage path : {P_DRIVE_PATH}")
    print(f"  Storage exists: {os.path.exists(P_DRIVE_PATH)}")
    print()
    if IS_RENDER:
        print("  Running on Render — check your service URL")
    else:
        print(f"  Portal    → http://localhost:{port}/portal")
        print(f"  Dashboard → http://localhost:{port}/dashboard")
        print(f"  Health    → http://localhost:{port}/health")
    print("=" * 55)

    # Create storage folder if it doesn't exist
    os.makedirs(P_DRIVE_PATH, exist_ok=True)

    # Use debug=False on Render, True locally
    app.run(host="0.0.0.0", port=port, debug=not IS_RENDER)