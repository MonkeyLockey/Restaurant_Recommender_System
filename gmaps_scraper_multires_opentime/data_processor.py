import pandas as pd
import json
import re
from collections import Counter
import os


def get_restaurant_tags(all_review_texts):
    """
    根據合併的評論文本，為餐廳生成食物類型和優先級標籤。
    Args:
        all_review_texts (str): 該餐廳所有評論的合併文本。
    Returns:
        tuple: (food_type_tag_list, priority_tags_list)
    """
    food_type_tags = []
    priority_tags = []

    # 將文本轉為小寫以便匹配
    text_lower = all_review_texts.lower()

    # --- 食物類型標籤 (擴展後) ---
    food_keywords = {
        'Italian': ['pasta', 'pizza', 'italian food', 'risotto', 'lasagna', 'tiramisu', 'gelato', 'calzone',
                    'antipasto'],
        'Chinese': ['noodles', 'dumplings', 'fried rice', 'sichuan', 'cantonese', 'chinese food', 'dim sum', 'wonton',
                    'chow mein', 'sweet and sour', 'spring rolls', 'dezhou chicken', 'biangbiang noodles',
                    'braised chicken', 'hand pulled noodles'],
        'Indian': ['curry', 'naan', 'tikka', 'masala', 'indian food', 'bhaji', 'samosa', 'biryani', 'rogan josh',
                   'tandoori', 'dosa', 'puri', 'south indian food'],
        'Japanese': ['sushi', 'ramen', 'sashimi', 'tempura', 'japanese food', 'udon', 'teriyaki', 'miso', 'nigiri',
                     'sake', 'chicken noodle'],
        'Mexican': ['taco', 'burrito', 'nachos', 'mexican food', 'quesadilla', 'guacamole', 'salsa', 'enchilada',
                    'fajita'],
        'Burger': ['burger', 'fries', 'cheeseburger', 'patty', 'bun', 'sliders'],
        'Cafe': ['coffee', 'latte', 'cappuccino', 'bakery', 'cake', 'cafe', 'espresso', 'pastry', 'sandwich', 'brunch',
                 'breakfast', 'frappe', 'bagel', 'chai'],
        'Bar/Pub': ['beer', 'cocktail', 'pub', 'drinks', 'bar', 'ale', 'lager', 'wine', 'spirits', 'pint', 'happy hour',
                    'gin', 'club', 'night out'],
        'Fast Food': ['fast food', 'takeaway', 'quick bite', 'drive-thru', 'delivery', 'fried chicken', 'chips', 'subs',
                      'sandwich'],
        'Vegetarian/Vegan': ['vegetarian', 'vegan', 'plant-based', 'meat-free', 'veggie', 'quorn'],
        'Thai': ['thai food', 'pad thai', 'green curry', 'red curry', 'tom yum', 'thai tofu'],
        'Mediterranean': ['mediterranean', 'hummus', 'falafel', 'kebab', 'pita', 'greek food', 'turkish food'],
        'Dessert': ['dessert', 'ice cream', 'chocolate', 'pudding', 'sweet', 'lemon posset', 'tiramisu'],
        'Seafood': ['seafood', 'fish', 'prawns', 'lobster', 'oysters', 'mussels', 'crab', 'salmon'],
        'Vietnamese': ['vietnamese', 'pho', 'bun-cha-ha-noi', 'duck dumplings', 'spring roll', 'lemongrass chicken'],
        'Ethiopian': ['ethiopian food', 'wot', 'tej', 'blue nile specialty', 'tilapia fish', 'platter'],
        'Spanish': ['spanish food', 'tapas', 'paella', 'meatballs', 'cannelloni', 'semifredo'],
        'Indian Street Food': ['dosa', 'puri', 'samosa', 'bhaji', 'chaat'],
        'Breakfast': ['breakfast', 'full english', 'omelette', 'bacon bap']
    }

    for food_type, keywords in food_keywords.items():
        if any(keyword in text_lower for keyword in keywords):
            food_type_tags.append(food_type)

    if not food_type_tags:
        food_type_tags.append('General Cuisine')

    # --- 優先級/方面標籤 (擴展後) ---
    aspect_keywords = {
        'Service': ['service', 'staff', 'waiter', 'waitress', 'friendly', 'rude', 'slow', 'attentive', 'polite',
                    'helpful', 'unresponsive', 'customer service', 'courtesy', 'served', 'team'],
        'Food Quality': ['food', 'taste', 'delicious', 'tasty', 'flavour', 'quality', 'cold', 'bland', 'fresh', 'hot',
                         'portion', 'menu', 'dishes', 'ingredients', 'overcooked', 'undercooked', 'authentic', 'dry',
                         'hard', 'flavourful', 'succulent', 'inedible', 'crispiness', 'filling', 'seasoning'],
        'Atmosphere': ['atmosphere', 'ambiance', 'cozy', 'loud', 'noisy', 'decor', 'vibe', 'lighting', 'music',
                       'comfortable', 'crowded', 'spacious', 'romantic', 'chilled', 'traditional', 'modern', 'private',
                       'community'],
        'Value': ['price', 'expensive', 'cheap', 'value for money', 'affordable', 'cost', 'bill', 'overpriced',
                  'bargain'],
        'Cleanliness': ['clean', 'dirty', 'hygiene', 'toilet', 'restroom', 'table', 'utensils'],
        'Location': ['location', 'convenient', 'easy to find', 'parking', 'accessible', 'central', 'hidden',
                     'proximity', 'situated'],
        'Waiting Time': ['wait', 'waiting', 'queue', 'slow service', 'fast service', 'quick service', 'rapid service'],
        'Drinks': ['drinks', 'cocktails', 'wine list', 'beer selection', 'coffee', 'tea', 'mocktails', 'ale', 'lager',
                   'frappe', 'flat white'],
        'Experience': ['experience', 'enjoyed', 'disappointed', 'loved', 'hated', 'overall', 'memorable', 'fun',
                       'uncomfortable', 'dreadful'],
        'Portion Size': ['portion', 'size', 'generous', 'small', 'big', 'filling'],
        'Dietary Options': ['vegan options', 'vegetarian options', 'gluten-free', 'allergies', 'halal', 'non halal'],
        'Seating/Comfort': ['uncomfortable', 'chairs', 'booth', 'sitting area', 'garden'],
        'Booking/Entry': ['booked', 'entry', 'bouncers', 'queue', 'discrimination'],
        'Communication/Responsiveness': ['email', 'response', 'unresponsive', 'complaint'],
        'Sound/Noise': ['music', 'loud', 'noisy', 'acoustics'],
        'Ventilation/AC': ['air conditioning', 'air circulation', 'hot', 'fan', 'ventilation']
    }

    for aspect, keywords in aspect_keywords.items():
        if any(keyword in text_lower for keyword in keywords):
            priority_tags.append(aspect)

    return food_type_tags, priority_tags


def process_and_tag_data(sentiment_csv_filename):
    """
    載入帶有情緒分析結果的CSV，聚合數據並為餐廳打標籤。
    Args:
        sentiment_csv_filename (str): 帶有情緒分析結果的CSV檔案路徑。
    Returns:
        pd.DataFrame: 處理並標註後的餐廳數據。
    """
    print(f"\n--- 開始處理數據並為餐廳打標籤 ---")
    print(f"正在載入情緒分析結果檔案: '{sentiment_csv_filename}'")

    if not os.path.exists(sentiment_csv_filename):
        print(f"錯誤: 找不到檔案 '{sentiment_csv_filename}'。請確認檔案路徑和名稱是否正確。")
        return pd.DataFrame()

    try:
        df_sentiment = pd.read_csv(sentiment_csv_filename, encoding='utf-8-sig', engine='python')
        print(f"成功載入 {len(df_sentiment)} 條評論數據。")
    except Exception as e:
        print(f"載入CSV檔案時發生錯誤: {e}")
        print("請檢查檔案編碼或內容格式。")
        return pd.DataFrame()

    # 確保 'review_text' 列是字串類型，並處理缺失值
    if 'review_text' in df_sentiment.columns:
        df_sentiment['review_text'] = df_sentiment['review_text'].astype(str).fillna('')
    else:
        print("警告: CSV檔案中沒有 'review_text' 列。無法進行評論文本分析。")
        return pd.DataFrame()

    # --- 聚合每家餐廳的數據 ---
    print("\n正在聚合每家餐廳的評論數據...")
    aggregated_df = df_sentiment.groupby('place_id').agg(
        restaurant_name=('restaurant_name', 'first'),
        address=('address', 'first'),
        avg_rating=('rating', 'first'),
        avg_sentiment_compound=('sentiment_compound', 'mean'),
        total_reviews=('review_text', 'count'),
        positive_review_count=('sentiment_label', lambda x: (x == 'Positive').sum()),
        negative_review_count=('sentiment_label', lambda x: (x == 'Negative').sum()),
        neutral_review_count=('sentiment_label', lambda x: (x == 'Neutral').sum()),
        opening_hours=('opening_hours', 'first'),
        all_review_texts=('review_text', lambda x: " ".join(x.dropna().tolist()))
    ).reset_index()

    aggregated_df['positive_ratio'] = aggregated_df['positive_review_count'] / aggregated_df['total_reviews']
    aggregated_df['negative_ratio'] = aggregated_df['negative_review_count'] / aggregated_df['total_reviews']
    aggregated_df[['positive_ratio', 'negative_ratio']] = aggregated_df[['positive_ratio', 'negative_ratio']].fillna(0)

    print(f"已聚合 {len(aggregated_df)} 家獨特地點的數據。")
    print("\n聚合數據預覽:")
    print(aggregated_df.head())

    # --- 應用關鍵詞標記器 ---
    print("\n正在為餐廳打標籤 (食物類型和優先級)...")
    tags_result = aggregated_df['all_review_texts'].apply(get_restaurant_tags)
    aggregated_df['food_type_tags'] = tags_result.apply(lambda x: x[0])
    aggregated_df['priority_tags'] = tags_result.apply(lambda x: x[1])

    # --- 新增: 將 food_type_tags 和 priority_tags 序列化為 JSON 字串 ---
    aggregated_df['food_type_tags'] = aggregated_df['food_type_tags'].apply(json.dumps)
    aggregated_df['priority_tags'] = aggregated_df['priority_tags'].apply(json.dumps)
    # 營業時間在 core.py 已經處理為 JSON 字串，這裡無需再次處理，但可以確保
    # aggregated_df['opening_hours'] = aggregated_df['opening_hours'].apply(lambda x: json.dumps(x) if isinstance(x, list) else x)
    # 上面這行如果 opening_hours 在聚合前已經是 JSON 字串，則無需再次 dumps
    # 如果 opening_hours 在聚合後變成了列表，則需要 dumps
    # 由於 core.py 已經 dumps 了，這裡應該是字串，所以無需再 dumps
    # 但為了健壯性，可以確保它始終是字串
    aggregated_df['opening_hours'] = aggregated_df['opening_hours'].apply(
        lambda x: x if isinstance(x, str) else json.dumps(x) if isinstance(x, list) else 'N/A')

    print("標籤完成！")
    print("\n帶有標籤的數據預覽:")
    print(aggregated_df[
              ['restaurant_name', 'food_type_tags', 'priority_tags', 'avg_rating', 'avg_sentiment_compound']].head())

    # --- 保存處理後的數據 ---
    output_processed_csv = sentiment_csv_filename.replace("_sentiment.csv", "_processed.csv")
    aggregated_df.to_csv(output_processed_csv, index=False, encoding='utf-8-sig')
    print(f"\n處理後的餐廳數據已保存至: {output_processed_csv}")

    return aggregated_df


if __name__ == "__main__":
    sentiment_csv_to_process = "birmingham_restaurants_20250718_012402_sentiment.csv"
    processed_data = process_and_tag_data(sentiment_csv_to_process)
    if not processed_data.empty:
        print("\n數據處理和標籤化成功完成！")