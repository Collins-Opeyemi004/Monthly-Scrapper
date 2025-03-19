import time
import json
import requests
import schedule
import threading
from flask import Flask, jsonify
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

app = Flask(__name__)

WEBHOOK_URL_MONTHLY = "https://hook.us2.make.com/a6mjvisd3ktkdvtus4t3ggi2egqbru6m"

monthly_leaderboard_data = []  # Stores latest monthly leaderboard data

def scrape_monthly_leaderboard():
    global monthly_leaderboard_data

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            url = "https://kolscan.io/leaderboard"
            page.goto(url, timeout=60000)
            
            # Wait for leaderboard page to load
            page.wait_for_selector(".leaderboard_leaderboardUser__8OZpJ", timeout=15000)
            print("✅ Monthly Leaderboard page loaded.")

            # Click the Monthly tab
            print("🔄 Switching to Monthly tab...")
            page.click("text=Monthly")
            time.sleep(2)  # Allow UI update

            # Wait for Monthly leaderboard to load
            print("⏳ Waiting for Monthly leaderboard to load...")
            page.wait_for_selector(".leaderboard_firstPlace__AShOl", timeout=10000)
            print("✅ Monthly leaderboard data detected!")
            
            players = page.query_selector_all(".leaderboard_leaderboardUser__8OZpJ")
            print(f"✅ Found {len(players)} players on the Monthly leaderboard.")

            if not players:
                print("⚠️ No Monthly leaderboard data found. Page structure might have changed.")
                return

            leaderboard = []

            for index, player in enumerate(players, start=1):
                try:
                    profile_img = player.query_selector("img").get_attribute("src")
                    profile_url = player.query_selector("a").get_attribute("href")
                    wallet_address = profile_url.split("/account/")[-1] if "/account/" in profile_url else "N/A"

                    name_elements = player.query_selector_all("h1")
                    if index == 1:
                        name = name_elements[0].inner_text().strip() if len(name_elements) > 0 else f"Rank {index}"
                    else:
                        name = name_elements[1].inner_text().strip() if len(name_elements) > 1 else f"Rank {index}"

                    win_loss = player.query_selector_all(".remove-mobile")
                    wins, losses = win_loss[1].inner_text().split("/") if len(win_loss) > 1 else ("0", "0")

                    sol_profit_element = player.query_selector(".leaderboard_totalProfitNum__HzfFO")
                    sol_number = sol_profit_element.query_selector_all("h1")[0].inner_text().strip()
                    dollar_value = sol_profit_element.query_selector_all("h1")[1].inner_text().strip()

                    # --- Step 7: Extract the Twitter/X URL by clicking the icon ---
                    x_profile_url = "N/A"
                    try:
                        icon = player.query_selector("img[src*='Twitter.webp'], img[src*='twitter.png']")
                        if icon:
                            try:
                                with page.expect_popup(timeout=3000) as popup_info:
                                    icon.click(force=True)
                                popup_page = popup_info.value
                                x_url = popup_page.url
                                popup_page.close()
                                if "twitter.com" in x_url or "x.com" in x_url:
                                    x_profile_url = x_url
                            except Exception:
                                try:
                                    with page.expect_navigation(timeout=3000):
                                        icon.click(force=True)
                                    new_url = page.url
                                    if "twitter.com" in new_url or "x.com" in new_url:
                                        x_profile_url = new_url
                                        page.go_back()
                                except Exception:
                                    x_profile_url = "N/A"
                    except Exception as e:
                        print(f"❌ Error extracting X profile for rank {index}: {e}")
                    
                    leaderboard.append({
                        "rank": index,
                        "profile_icon": profile_img,
                        "name": name,
                        "profile_url": profile_url,
                        "wallet_address": wallet_address,
                        "wins": wins.strip(),
                        "losses": losses.strip(),
                        "sol_number": sol_number.strip(),
                        "dollar_value": dollar_value.strip(),
                        "x_profile_url": x_profile_url
                    })
                except Exception as e:
                    print(f"❌ Error extracting Monthly data for rank {index}: {e}")
            
            monthly_leaderboard_data = leaderboard
            
            # Send data to webhook
            try:
                response = requests.post(WEBHOOK_URL_MONTHLY, json={"monthly_leaderboard": leaderboard})
                response.raise_for_status()
                print("✅ Monthly data sent successfully:", response.status_code)
            except requests.exceptions.RequestException as e:
                print("❌ Failed to send Monthly data:", e)
        
        finally:
            browser.close()

# Schedule job for monthly scraping (runs every 30 days at midnight)
schedule.every(30).days.at("00:00").do(scrape_monthly_leaderboard)

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)

threading.Thread(target=run_scheduler, daemon=True).start()

@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "Kolscan Monthly Scraper is running! Use /scrape_monthly to trigger scraping."})

@app.route("/scrape_monthly", methods=["GET"])
def manual_scrape_monthly():
    scrape_monthly_leaderboard()
    return jsonify({"message": "Monthly scraping triggered!", "data": monthly_leaderboard_data})

if __name__ == "__main__":
    # Changed port to 5000
    app.run(host="0.0.0.0", port=5002, debug=True)
