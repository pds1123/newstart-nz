import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ["MBIE_API_KEY"]
BASE_URL = "https://api.business.govt.nz/gateway/tenancy-services/market-rent/v2"

headers = {
    "Ocp-Apim-Subscription-Key": API_KEY,
    "Accept": "application/json"
}

def get_area_definitions():
    """Step 1: Find out what area definitions are available (e.g. suburb-level codes)."""
    url = f"{BASE_URL}/area-definitions"
    response = requests.get(url, headers=headers)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(json.dumps(data, indent=2)[:2000])
        return data
    else:
        print("Error:", response.text)
        return None

def get_statistics(period_ending="2024-12", num_months=1, area_definition="territorial-authority-2019"):
    """Step 2: Get actual rent statistics."""
    url = f"{BASE_URL}/statistics"
    params = {
        "period-ending": period_ending,
        "num-months": num_months,
        "area-definition": area_definition
    }
    response = requests.get(url, headers=headers, params=params)
    print(f"Status: {response.status_code}")
    print(f"URL called: {response.url}")
    if response.status_code == 200:
        data = response.json()
        print(json.dumps(data, indent=2)[:3000])
        return data
    else:
        print("Error:", response.text)
        return None

if __name__ == "__main__":
    print("=" * 60)
    print("STEP 1: Get area definitions")
    print("=" * 60)
    get_area_definitions()

    print()
    print("=" * 60)
    print("STEP 2: Get rent statistics (Territorial Authority level)")
    print("=" * 60)
    get_statistics()
