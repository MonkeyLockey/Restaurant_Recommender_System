import pandas as pd
from nltk.sentiment.vader import SentimentIntensityAnalyzer
import os
import json # 導入 json 模組來處理營業時間的 JSON 字串

def run_sentiment_analysis():
    # --- 配置您的 CSV 檔案路徑 ---
    # 請將這裡的檔案路徑替換為您實際抓取到的評論 CSV 檔案名
    # 例如: "birmingham_restaurants_20240718_134530.csv"
    csv_filename = "birmingham_restaurants_20250725_000229.csv"
    # -----------------------------

    # 檢查檔案是否存在
    if not os.path.exists(csv_filename):
        print(f"錯誤: 找不到檔案 '{csv_filename}'。請確認檔案路徑和名稱是否正確。")
        return

    # 使用 pandas 載入 CSV 檔案
    try:
        # 使用 utf-8-sig 編碼處理 BOM，engine='python' 提高兼容性
        df = pd.read_csv(csv_filename, encoding='utf-8-sig', engine='python')
        print(f"成功載入 {len(df)} 條評論數據。")
        print("\n載入數據預覽:")
        print(df.head())
    except Exception as e:
        print(f"載入CSV檔案時發生錯誤: {e}")
        print("請檢查檔案編碼或內容格式。")
        return

    # 確保 'review_text' 列是字串類型，並處理缺失值
    if 'review_text' in df.columns:
        df['review_text'] = df['review_text'].astype(str).fillna('')
        print("\n評論文本預處理完成 (處理缺失值)。")
    else:
        print("錯誤: CSV檔案中沒有 'review_text' 列。請確認CSV格式。")
        return

    # 初始化 VADER 情緒分析器
    analyzer = SentimentIntensityAnalyzer()

    # 創建用於儲存情緒分數的列
    df['sentiment_compound'] = 0.0
    df['sentiment_neg'] = 0.0
    df['sentiment_neu'] = 0.0
    df['sentiment_pos'] = 0.0
    df['sentiment_label'] = '' # 新增情感標籤

    # 對每條評論進行情緒分析
    print("\n開始進行情緒分析...")
    for index, row in df.iterrows():
        review_text = row['review_text']
        if review_text: # 只對非空評論進行分析
            vs = analyzer.polarity_scores(review_text)
            df.loc[index, 'sentiment_compound'] = vs['compound']
            df.loc[index, 'sentiment_neg'] = vs['neg']
            df.loc[index, 'sentiment_neu'] = vs['neu']
            df.loc[index, 'sentiment_pos'] = vs['pos']

            # 根據 compound score 判斷情感標籤
            if vs['compound'] >= 0.05:
                df.loc[index, 'sentiment_label'] = 'Positive'
            elif vs['compound'] <= -0.05:
                df.loc[index, 'sentiment_label'] = 'Negative'
            else:
                df.loc[index, 'sentiment_label'] = 'Neutral'
        else:
            # 對於空評論，設置為中立或無情感
            df.loc[index, 'sentiment_label'] = 'No Review'

    print("情緒分析完成！")
    print("\n帶有情緒分數的數據預覽:")
    print(df[['review_text', 'sentiment_neg', 'sentiment_neu', 'sentiment_pos', 'sentiment_compound', 'sentiment_label']].head())

    # --- 進一步分析和可視化 (可選) ---
    print("\n情緒標籤分佈:")
    print(df['sentiment_label'].value_counts())

    print("\n按地點名稱平均情緒分數 (僅顯示前5家):")
    if 'restaurant_name' in df.columns:
        # 先處理可能重複的 place_id，確保每個獨特地點只計算一次平均情緒
        # 這裡假設您希望按 'place_id' 來計算獨特地點的平均情緒
        # 如果一個地點有多條評論，我們會取這些評論的平均情緒
        unique_places_df = df.groupby('place_id').agg(
            restaurant_name=('restaurant_name', 'first'), # 取第一個名稱
            avg_sentiment_compound=('sentiment_compound', 'mean') # 計算平均情緒
        ).reset_index()

        avg_sentiment_per_place = unique_places_df.sort_values(by='avg_sentiment_compound', ascending=False)
        print(avg_sentiment_per_place[['restaurant_name', 'avg_sentiment_compound']].head(5))
        print("\n按地點名稱平均情緒分數 (僅顯示後5家):")
        print(avg_sentiment_per_place[['restaurant_name', 'avg_sentiment_compound']].tail(5))
    else:
        print("CSV檔案中沒有 'restaurant_name' 列，無法按地點分組。")
    # ------------------------------------

    # 您可以選擇將帶有情緒分數的數據保存到新的 CSV 檔案中
    output_sentiment_csv = csv_filename.replace(".csv", "_sentiment.csv")
    df.to_csv(output_sentiment_csv, index=False, encoding='utf-8-sig')
    print(f"\n帶有情緒分析結果的數據已保存至: {output_sentiment_csv}")


if __name__ == "__main__":
    run_sentiment_analysis()
