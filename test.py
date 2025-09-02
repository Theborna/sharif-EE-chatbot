import requests
from requests.auth import HTTPBasicAuth

# 1. ایجاد سشن و گرفتن session_id
create_session_url = "http://213.233.184.142:8020/create-session"
response = requests.post(create_session_url, auth=HTTPBasicAuth("admin", "admin"))
if response.status_code == 200:
    data = response.json()
    session_id = data.get("session_id")
    if not session_id:
        print("خطا: session_id دریافت نشد.")
        exit()
    print("Session ID:", session_id)
else:
    print("خطا در ایجاد سشن:", response.status_code)
    print(response.text)
    exit()

# 2. ارسال کوئری با session_id
query_url = "http://213.233.184.142:8020/query"
headers = {
    "Content-Type": "application/json"
}
payload = {
    "session_id": session_id,
    "query": "استاد آرش امینی چه سمتی در دانشکده دارد ؟"
}

response = requests.post(query_url, json=payload, headers=headers, auth=HTTPBasicAuth("admin", "admin"))
if response.status_code == 200:
    print("پاسخ API:", response.json())
else:
    print("خطا در ارسال کوئری:", response.status_code)
    print(response.text)
