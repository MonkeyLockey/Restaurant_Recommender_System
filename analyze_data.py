import pandas as pd
import os

# --- 配置您處理後的 CSV 檔案路徑 ---
# 這是 data_processor.py 輸出的檔案
PROCESSED_CSV_FILENAME = "birmingham_restaurants_20250725_000229_processed.csv"


# ------------------------------------

def analyze_review_counts(filename):
    if not os.path.exists(filename):
        print(f"錯誤: 找不到檔案 '{filename}'。請確認檔案路徑和名稱是否正確。")
        return

    try:
        df = pd.read_csv(filename, encoding='utf-8-sig', engine='python')

        # 確保 total_reviews 是數值類型
        df['total_reviews'] = pd.to_numeric(df['total_ratings'], errors='coerce').fillna(0).astype(int)

        print(f"\n--- 分析 '{filename}' 中餐廳的評論數量分佈 ---")

        # 顯示基本統計信息
        print("\n評論數量 (total_reviews) 的基本統計:")
        print(df['total_reviews'].describe())

        # 顯示評論數量的前幾位和後幾位的餐廳
        print("\n評論數量最多的前10家餐廳:")
        print(df.sort_values(by='total_reviews', ascending=False).head(10)[['restaurant_name', 'total_reviews']])

        print("\n評論數量最少 (非零) 的前10家餐廳:")
        print(df[df['total_reviews'] > 0].sort_values(by='total_reviews', ascending=True).head(10)[
                  ['restaurant_name', 'total_reviews']])

        # 檢查不同閾值下的餐廳數量
        print(f"\n--- 不同評論數量閾值下的餐廳數量 ---")
        thresholds = [1, 5, 10, 20, 30, 50, 60, 100]
        for threshold in thresholds:
            count = df[df['total_reviews'] >= threshold].shape[0]
            total_restaurants = df.shape[0]
            percentage = (count / total_restaurants * 100) if total_restaurants > 0 else 0
            print(f"評論數 >= {threshold} 的餐廳數量: {count} 家 ({percentage:.2f}%)")

    except Exception as e:
        print(f"分析評論數量時發生錯誤: {e}")
        print("請檢查檔案內容或格式。")


if __name__ == "__main__":
    analyze_review_counts(PROCESSED_CSV_FILENAME)
