import pandas as pd
import json
import os
import re  # 用於處理用戶輸入和文本匹配


def load_processed_data(filename):
    """
    載入處理後的餐廳數據。
    Args:
        filename (str): 處理後的CSV檔案路徑。
    Returns:
        pd.DataFrame: 載入的數據。
    """
    if not os.path.exists(filename):
        print(f"錯誤: 找不到檔案 '{filename}'。請確認檔案路徑和名稱是否正確。")
        return pd.DataFrame()
    try:
        df = pd.read_csv(filename, encoding='utf-8-sig', engine='python')

        # --- 新增: 更健壯的 JSON 字串解析輔助函式 ---
        def parse_json_list(s):
            # 如果值是 NaN (Not a Number) 或者空字串，則返回空列表
            if pd.isna(s) or s == '':
                return []
            try:
                # 嘗試解析 JSON 字串
                return json.loads(s)
            except json.JSONDecodeError as e:
                # 如果解析失敗，打印警告並返回空列表
                print(f"警告: 解析 JSON 錯誤 '{e}'。原始字串: '{s}'。將返回空列表。")
                return []
            except Exception as e:
                # 捕獲其他未知錯誤
                print(f"警告: 未知錯誤 '{e}' 解析字串: '{s}'。將返回空列表。")
                return []

        # ------------------------------------------------

        # 將儲存為字串的列表轉換回 Python 列表
        df['food_type_tags'] = df['food_type_tags'].apply(parse_json_list)
        df['priority_tags'] = df['priority_tags'].apply(parse_json_list)
        # 也將 opening_hours 轉換，因為它也是 JSON 字串
        df['opening_hours'] = df['opening_hours'].apply(parse_json_list)

        print(f"成功載入 {len(df)} 家餐廳數據用於推薦。")
        return df
    except Exception as e:
        print(f"載入 processed CSV 檔案時發生錯誤: {e}")
        print("請檢查檔案編碼或內容格式。")
        return pd.DataFrame()


def get_user_preferences():
    """
    從用戶獲取推薦偏好。
    Returns:
        dict: 包含用戶偏好的字典。
    """
    print("\n=== 請輸入您的推薦偏好 ===")
    food_preference = input("您想吃什麼食物類型？ (例如: Italian, Chinese, Cafe, Burger, Seafood, 或留空): ").strip()
    mood = input("您希望餐廳氛圍如何？ (例如: quiet, lively, romantic, cozy, 或留空): ").strip()
    priority = input("您最注重什麼？ (例如: Service, Food Quality, Atmosphere, Value, Cleanliness, 或留空): ").strip()
    location = input("您希望在哪個區域搜尋？ (例如: Birmingham City Centre, Selly Oak, 或留空): ").strip()

    return {
        'food_preference': food_preference if food_preference else None,
        'mood': mood if mood else None,
        'priority': priority if priority else None,
        'location': location if location else None
    }


def recommend_restaurants(restaurant_df, user_preferences, top_n=5):
    """
    根據用戶偏好推薦餐廳。
    Args:
        restaurant_df (pd.DataFrame): 包含餐廳聚合數據的DataFrame。
        user_preferences (dict): 包含用戶偏好的字典。
        top_n (int): 推薦數量。
    Returns:
        pd.DataFrame: 推薦的餐廳列表。
    """
    filtered_df = restaurant_df.copy()

    # --- 1. 過濾階段 ---

    # 按食物類型過濾
    if user_preferences['food_preference']:
        food_pref_lower = user_preferences['food_preference'].lower()
        # 確保 tags 列表不為空，且其中有匹配項
        filtered_df = filtered_df[
            filtered_df['food_type_tags'].apply(
                lambda tags: any(food_pref_lower in tag.lower() for tag in tags if isinstance(tag, str)))
        ]
        if filtered_df.empty:
            print(f"沒有找到符合 '{user_preferences['food_preference']}' 食物偏好的餐廳。")
            return pd.DataFrame()

    # 按地點過濾 (簡單匹配地址)
    if user_preferences['location']:
        location_lower = user_preferences['location'].lower()
        filtered_df = filtered_df[
            filtered_df['address'].str.contains(location_lower, case=False, na=False)
        ]
        if filtered_df.empty:
            print(f"在 '{user_preferences['location']}' 附近沒有找到符合條件的餐廳。")
            return pd.DataFrame()

    if filtered_df.empty:
        print("經過過濾後，沒有找到任何符合基本條件的餐廳。")
        return pd.DataFrame()

    # --- 2. 評分階段 ---
    filtered_df['recommendation_score'] = 0.0

    # 基礎分數：平均星級和平均情緒分數 (給予權重)
    # 將 avg_rating 歸一化到 0-1 範圍 (假設評分是 1-5)
    filtered_df['normalized_rating'] = filtered_df['avg_rating'] / 5.0
    # 將 avg_sentiment_compound 歸一化到 0-1 範圍 (從 -1 到 1 映射到 0 到 1)
    filtered_df['normalized_sentiment'] = (filtered_df['avg_sentiment_compound'] + 1) / 2.0

    # 權重可以調整
    filtered_df['recommendation_score'] += filtered_df['normalized_rating'] * 0.5
    filtered_df['recommendation_score'] += filtered_df['normalized_sentiment'] * 0.5

    # 加分項：心情/氛圍匹配 (基於評論文本中的關鍵詞和情緒)
    if user_preferences['mood']:
        mood_lower = user_preferences['mood'].lower()
        mood_keywords = {
            'quiet': ['quiet', 'peaceful', 'calm', 'relaxing'],
            'lively': ['lively', 'noisy', 'busy', 'energetic', 'vibrant'],
            'romantic': ['romantic', 'intimate', 'date night'],
            'cozy': ['cozy', 'warm', 'comfortable', 'homely']
        }

        if mood_lower in mood_keywords:
            for keyword in mood_keywords[mood_lower]:
                # 匹配評論文本中包含關鍵詞的，並考慮其正面情緒比例
                filtered_df['recommendation_score'] += (
                        filtered_df['all_review_texts'].str.contains(keyword, case=False, na=False) * filtered_df[
                    'positive_ratio'] * 0.1
                )

    # 加分項：注重事項匹配 (基於 priority_tags 和情緒)
    if user_preferences['priority']:
        priority_lower = user_preferences['priority'].lower()
        filtered_df['recommendation_score'] += (
                filtered_df['priority_tags'].apply(
                    lambda tags: any(priority_lower in tag.lower() for tag in tags if isinstance(tag, str))) *
                filtered_df['positive_ratio'] * 0.2
        )

    # --- 3. 排序並返回 Top N ---
    recommended_df = filtered_df.sort_values(by='recommendation_score', ascending=False).head(top_n)

    if recommended_df.empty:
        print("沒有找到符合您所有偏好的推薦餐廳。請嘗試放寬條件。")
        return pd.DataFrame()

    return recommended_df[[
        'restaurant_name', 'address', 'avg_rating', 'avg_sentiment_compound',
        'food_type_tags', 'priority_tags', 'recommendation_score', 'opening_hours'
    ]]


# --- 主執行區塊 ---
if __name__ == "__main__":
    # --- 配置您處理後的 CSV 檔案路徑 ---
    # 這是 data_processor.py 輸出的檔案
    processed_csv_filename = "birmingham_restaurants_20250718_012402_processed.csv"  # <--- 替換為您的檔案名
    # ------------------------------------

    # 載入數據
    restaurant_data = load_processed_data(processed_csv_filename)

    if not restaurant_data.empty:
        # 獲取用戶偏好
        user_prefs = get_user_preferences()

        # 進行推薦
        print("\n=== 正在為您推薦餐廳... ===")
        recommendations = recommend_restaurants(restaurant_data, user_prefs, top_n=5)

        # 呈現推薦結果
        if not recommendations.empty:
            print("\n=== 推薦結果 ===")
            for i, row in recommendations.iterrows():
                print(f"\n--- 推薦 {i + 1} ---")
                print(f"名稱: {row['restaurant_name']}")
                print(f"地址: {row['address']}")
                print(f"平均星級: {row['avg_rating']:.1f}")
                print(f"平均情緒分數: {row['avg_sentiment_compound']:.2f}")
                print(f"食物類型: {', '.join(row['food_type_tags'])}")
                print(f"注重方面: {', '.join(row['priority_tags'])}")
                print(f"推薦分數: {row['recommendation_score']:.2f}")

                # 解碼並顯示營業時間
                try:
                    # 確保 row['opening_hours'] 是一個列表，因為 parse_json_list 已經處理過了
                    if isinstance(row['opening_hours'], list):
                        print("營業時間:")
                        for hour_entry in row['opening_hours']:
                            print(f"  - {hour_entry}")
                    else:
                        print(f"營業時間: {row['opening_hours']}")  # 如果不是列表，就直接打印原始字串
                except Exception as e:
                    print(f"顯示營業時間時發生錯誤: {e}. 原始數據: {row['opening_hours']}")
        else:
            print("\n很抱歉，沒有找到符合您所有偏好的推薦餐廳。")
            print("請嘗試重新運行程式並放寬您的搜尋條件，例如：")
            print("- 減少食物類型或注重事項的具體性。")
            print("- 嘗試不同的心情描述。")
            print("- 移除地點限制。")
