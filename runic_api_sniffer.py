from playwright.sync_api import sync_playwright
import json

BASE = "https://chaos-agents.popularium.com"
MARKET_URL = f"{BASE}/agents?agentsTab=market"
LOGIN_URL = f"{BASE}/login"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # ----------------------------
        # STEP 1: LOGIN
        # ----------------------------
        page.goto(LOGIN_URL)

        input("\n👉 Log in manually in the browser, THEN press ENTER here...\n")

        # ----------------------------
        # STEP 2: INTERCEPT ALL API TRAFFIC to find
        # ----------------------------
        def handle_response(response):
            try:
                ct = response.headers.get("content-type", "")

                # only care about JSON APIs
                if "application/json" not in ct:
                    return

                url = response.url

                # filter out noise
                if any(x in url for x in ["google", "analytics", "settings"]):
                    return

                print("\n==============================")
                print("URL:", url)
                print("STATUS:", response.status)

                data = response.json()
                print("TYPE:", type(data))

                # show small preview
                print("PREVIEW:", str(data)[:500])

            except Exception as e:
                print("ERROR parsing response:", e)

        page.on("response", handle_response)

        # ----------------------------
        # STEP 3: LOAD MARKET PAGE
        # ----------------------------
        print("\n👉 Loading market page...\n")

        page.goto(MARKET_URL, wait_until="domcontentloaded")

        # give React time to fire all requests
        page.wait_for_timeout(10000)

        print("\n✅ Done sniffing. Check output above for agent list endpoint.\n")

        browser.close()


if __name__ == "__main__":
    main()