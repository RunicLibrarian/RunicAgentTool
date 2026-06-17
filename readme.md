# Runic Agent Tool

This folder contains a Python scraper for the Chaos Agents market.

## Setup

Install Playwright:

```bash
pip install playwright
playwright install chromium
```

## Run

```bash
python scrape_agents.py --output agents.csv
```

The script opens a visible browser, takes you to the Chaos Agents login page, waits for you to sign in manually, and then exports each agent and its skills to CSV.