from __future__ import annotations
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import csv
import time
from pathlib import Path
from typing import Dict, Any, List
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import requests

from playwright.sync_api import sync_playwright


# ----------------------------
# CONFIG
# ----------------------------

BASE = "https://chaos-agents.popularium.com"
LOGIN_URL = f"{BASE}/login"
MARKET_API = f"{BASE}/api/agents/list/bench"

OUTPUT_FILE = Path("agents_wide.csv")
MAX_WORKERS = 12


# ----------------------------
# STEP 1: LOGIN + EXTRACT TOKEN
# ----------------------------

def get_auth_token() -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        page.goto(LOGIN_URL)
        input("Login manually, then press ENTER...")

        token = page.evaluate("""
        () => {
            const raw = localStorage.getItem("chaos-agents:tokens");
            if (!raw) return null;
            try {
                return JSON.parse(raw).access;
            } catch (e) {
                return null;
            }
        }
        """)

        browser.close()

    if not token:
        raise RuntimeError("Failed to extract auth token")

    print("Token extracted ✓")
    return token


# ----------------------------
# HEADERS
# ----------------------------

def headers(token: str) -> Dict[str, str]:
    return {
        "Accept": "application/json",
        "X-App-Origin": "Web",
        "Authorization": f"Bearer {token}",
    }


# ----------------------------
# STEP 2: FETCH AGENT IDS
# ----------------------------

def fetch_all_agents(token: str):
    agents = []
    page = 1

    while True:
        r = requests.get(
            MARKET_API,
            params={"page": page, "player": "current"},
            headers=headers(token),
        )

        if r.status_code != 200:
            print("Stopped:", r.status_code, r.text[:200])
            break
        r.encoding = "utf-8"
        data = r.json()
        items = data.get("data", [])

        if not items:
            break

        for item in items:
            unit = item.get("game_unit") or {}

            agent_id = unit.get("id")
            if not agent_id:
                continue

            agent_name = (
                unit.get("friendly_name")
                or unit.get("full_name")
                or "Unknown"
            )

            agents.append({
                "id": str(agent_id),
                "name": agent_name
            })

        print(f"Page {page}: {len(items)} items | total={len(agents)}")
        page += 1

    return agents


# ----------------------------
# STEP 3: SKILL MAP FETCH
# ----------------------------

def fetch_skill_map(token: str, agent_id: str):
    r = requests.get(
        f"{BASE}/api/agents/{agent_id}/skill-map",
        headers=headers(token),
    )

    if r.status_code != 200:
        raise RuntimeError(f"{agent_id}: {r.status_code}")
    r.encoding = "utf-8"
    return r.json()

# ----------------------------
# STEP 5: PARALLEL FETCH
# ----------------------------

def fetch_all_skill_maps(token: str, agents):
    results = {}

    def task(agent):
        skill_map = fetch_skill_map(token, agent["id"])
        return agent["id"], agent["name"], skill_map

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(task, a) for a in agents]

        for f in as_completed(futures):
            try:
                aid, name, skill_map = f.result()

                results[aid] = {
                    "agent_name": name,
                    "skill_map": skill_map
                }

                print("OK", aid)

            except Exception as e:
                print("Skip:", e)

    return results


# ----------------------------
# STEP 6: WRITE CSV
# ----------------------------
SKILL_CLASSES = [
    "Assassin",
    "Berserker",
    "Biosculptor",
    "Engineer",
    "Explorer",
    "Sniper",
    "Paladin",
    "Sentinel",
    "Trapmaster",
]

SLOTS_PER_CLASS = 12  # 1.1–1.6 + 2.1–2.6

def build_header():
    header = ["agent_id", "agent_name"]

    for cls in SKILL_CLASSES:
        for i in range(1, 7):
            header.append(f"{cls} 1.{i}")
        for i in range(1, 7):
            header.append(f"{cls} Slot 2.{i}")

    return header

CLASS_MAP = {
    "SCLSEXPLORE": "Explorer",
    "SCLSPALADIN": "Paladin",
    "SCLSBIOSCLPT": "Biosculptor",
    "SCLSASSASIN": "Assassin",
    "SCLSENGINEER": "Engineer",
    "SCLSSENTINL": "Sentinel",
    "SCLSTRAPMSTR": "Trapmaster",
    "SCLSBERSRKR": "Berserker",
    "SCLSSNIPER": "Sniper",
}
def normalize_class(raw: str) -> str:
    return CLASS_MAP.get(raw, raw)

def build_agent_row(agent_id: str, agent_name: str, skill_map: list[dict]):
    row = [agent_id, agent_name]

    matrix = {
        cls: [""] * SLOTS_PER_CLASS
        for cls in SKILL_CLASSES
    }

    for entry in skill_map:
        if not isinstance(entry, dict):
            continue

        cls = normalize_class(entry.get("skill_class"))
        if cls not in matrix:
            continue

        skills = entry.get("skills", [])
        if not isinstance(skills, list):
            continue

        names = []

        # 🔥 IMPORTANT FIX: skills is list of lists
        for group in skills:
            if not isinstance(group, list):
                continue

            for skill in group:
                if not isinstance(skill, dict):
                    continue

                name = skill.get("skill_name")
                if name:
                    names.append(name)

        # fill slots
        for i in range(min(SLOTS_PER_CLASS, len(names))):
            matrix[cls][i] = names[i]

    for cls in SKILL_CLASSES:
        row.extend(matrix[cls])

    return row

def clean(value):
    if value is None:
        return ""

    if isinstance(value, (dict, list)):
        return str(value)

    return str(value).replace("\u201c", '"').replace("\u201d", '"')

def build_row(item):
    agent_id, row_data = item

    agent_name = row_data.get("agent_name", "Unknown")
    skill_map = row_data.get("skill_map", [])

    row = build_agent_row(agent_id, agent_name, skill_map)

    return [clean(x) for x in row]

def write_csv(results: dict):
    header = build_header()

    with OUTPUT_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)

        with ThreadPoolExecutor(max_workers=8) as ex:
            rows = ex.map(build_row, results.items())
            writer.writerows(rows)

# ----------------------------
# MAIN
# ----------------------------

def main():
    token = get_auth_token()

    print("\nFetching agents...")
    agents = fetch_all_agents(token)

    print("\nTotal agents:", len(agents))

    print("\nFetching skill maps (parallel)...")
    results = fetch_all_skill_maps(token, agents)

    print("\nWriting CSV...")
    write_csv(results)

    print("Done → agents_wide.csv")


if __name__ == "__main__":
    main()