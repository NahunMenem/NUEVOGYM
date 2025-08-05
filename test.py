import requests
from requests.auth import HTTPDigestAuth
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

payload = {
    "UserInfo": {
        "employeeNo": "1003",
        "name": "Sin RightPlan",
        "userType": "normal",
        "Valid": {
            "enable": True,
            "beginTime": "2024-01-01T00:00:00",
            "endTime": "2030-01-01T23:59:59"
        },
        "doorRight": "1"
    }
}

res = requests.post(
    "https://192.168.1.31/ISAPI/AccessControl/UserInfo/Record?format=json",
    json=payload,
    headers={"Content-Type": "application/json"},
    auth=HTTPDigestAuth("admin", "3804315721A"),
    verify=False
)

print(res.status_code)
print(res.text)
