import requests

API_KEY = "42be29e960b04eb3b9311e2eec443757"
username = "elonmusk"

headers = {
    "x-api-key": API_KEY
}

url = f"https://api.twitterapi.io/twitter/user/last_tweets?userName={username}&limit=1"

response = requests.get(url, headers=headers)

print(f"Status Code: {response.status_code}")
print("Response:")
print(response.text)
