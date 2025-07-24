import googlemaps
import os

# IMPORTANT: 請在這裡替換為您的實際 Google Maps API Key！
# 例如: api_key = "AIzaSyC..."
api_key = os.getenv("GOOGLE_MAPS_API_KEY")

if api_key == "YOUR_GOOGLE_MAPS_API_KEY_HERE" or not api_key:
    print("錯誤：請在程式碼中填寫您的 Google Maps API Key。")
    print("請將 'YOUR_GOOGLE_MAPS_API_KEY_HERE' 替換為您的實際 API Key。")
    exit()

try:
    print("正在初始化 Google Maps 客戶端...")
    gmaps = googlemaps.Client(key=api_key)
    print("客戶端初始化完成。")

    print("正在嘗試進行一個簡單的地理編碼呼叫...")
    # 嘗試一個眾所周知的位置
    geocode_result = gmaps.geocode("London, UK")

    if geocode_result:
        print("地理編碼呼叫成功！")
        print(f"倫敦的座標：{geocode_result[0]['geometry']['location']}")
    else:
        print("地理編碼呼叫沒有返回任何結果。")

except googlemaps.exceptions.ApiError as e:
    print(f"Google Maps API 錯誤：{e}")
    print("請檢查您的 API Key 是否有效，以及是否已啟用相關的 API 服務（例如 Geocoding API）。")
except Exception as e:
    print(f"發生了意外錯誤：{e}")
    print("請檢查您的網路連線或防火牆設置。")

print("測試完成。")
