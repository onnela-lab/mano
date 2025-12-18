import requests
import orjson
import sys
import os
sys.path.insert(0, '')  
import keyring_studies 

ACCESS_KEY = os.environ.get("BEIWE_ACCESS_KEY")
SECRET_KEY = os.environ.get("BEIWE_SECRET_KEY")
MY_BEIWE_SERVER = os.environ.get("BEIWE_URL")

if not all([ACCESS_KEY, SECRET_KEY, MY_BEIWE_SERVER]):
    raise ValueError(
        "Missing required Beiwe credentials"
    )

print("Successfully loaded Beiwe credentials")
ENDPOINT_STUDY_SETTINGS = f"{MY_BEIWE_SERVER}/get-study-settings/v1"
ENDPOINT_INTERVENTIONS = f"{MY_BEIWE_SERVER}/get-interventions/v1"

def fetch_json(endpoint, study_id):
    response = requests.post(
        endpoint,
        data={
            "access_key": ACCESS_KEY,
            "secret_key": SECRET_KEY,
            "study_id": study_id
        },
        allow_redirects=False
    )

    if response.status_code == 403:
        raise PermissionError("403 Forbidden")
    if response.status_code == 400:
        raise RuntimeError("400 Bad Request")
    if response.status_code == 404:
        raise RuntimeError("404 Not Found")
    if response.status_code != 200:
        raise RuntimeError(f"Error {response.status_code}: {response.text[:200]}")
    
    return orjson.loads(response.content)

print("\nFetching study settings JSON...")
study_settings = fetch_json(ENDPOINT_STUDY_SETTINGS, study_id)
with open("study_config.json", "wb") as f:
    f.write(orjson.dumps(study_settings))
print("Saved study_config.json")

print("Fetching interventions JSON...")
interventions = fetch_json(ENDPOINT_INTERVENTIONS, study_id)
with open("interventions.json", "wb") as f:
    f.write(orjson.dumps(interventions))
print("Saved interventions.json")


""" 
Todo:
- Read the backfill and download functions
- Add tests and error messages for this file
- Write up some good documentation for the function I want to have, two functions download cofig/intervention
- Allow output directory
- Show useful error messages
- Should have type checking (see backfill, download, normalized_url)
- Work out what make sense for adopting this double function pattern, one validation one doing the thing
"""
