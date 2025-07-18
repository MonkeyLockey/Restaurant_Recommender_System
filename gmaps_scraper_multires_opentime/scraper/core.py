import googlemaps
import time
import csv
from datetime import datetime
import os
import random
import json
import logging  # 新增導入

# 獲取當前模組的 logger 實例
logger = logging.getLogger(__name__)


# 注意: 這裡不需要設定 level 或 handler，因為這些會在 run.py 中統一配置
# 這裡只需要獲取 logger，run.py 中的配置會應用到這裡

class RestaurantScraper:
    def __init__(self, api_key, existing_csv_filename=None):
        self.gmaps = googlemaps.Client(key=api_key)
        self.restaurants_data = []
        self.api_call_count = 0
        self.processed_place_ids = set()

        if existing_csv_filename and os.path.exists(existing_csv_filename):
            logger.info(f"正在從現有文件 '{existing_csv_filename}' 加載已處理的餐廳 ID...")
            try:
                with open(existing_csv_filename, 'r', newline='', encoding='utf-8-sig') as csvfile:
                    reader = csv.DictReader(csvfile)
                    if 'place_id' in reader.fieldnames:
                        for row in reader:
                            if row['place_id']:
                                self.processed_place_ids.add(row['place_id'])
                        logger.info(f"已加載 {len(self.processed_place_ids)} 個餐廳 ID。")
                    else:
                        logger.warning(
                            "警告: 現有CSV文件未包含 'place_id' 列，無法進行跨運行去重。請確保歷史文件包含 'place_id'。")
            except Exception as e:
                logger.error(f"從CSV加載ID時發生錯誤: {e}")

    def _make_api_call(self, api_method, *args, **kwargs):
        max_retries = 5
        base_delay = 1  # 實際運行建議 1 秒或以上
        for attempt in range(max_retries):
            try:
                result = api_method(*args, **kwargs)
                self.api_call_count += 1
                return result
            except googlemaps.exceptions.ApiError as e:
                error_message = str(e)
                logger.warning(f"API 呼叫失敗 (嘗試 {attempt + 1}/{max_retries}): {error_message}")
                if "OVER_QUERY_LIMIT" in error_message or "rate limit" in error_message.lower():
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"達到查詢限制，將在 {delay:.2f} 秒後重試...")
                    time.sleep(delay)
                elif "ZERO_RESULTS" in error_message:
                    logger.info("API 返回 ZERO_RESULTS，沒有找到結果。")
                    return None
                else:
                    raise
            except Exception as e:
                logger.error(f"發生未知錯誤 (嘗試 {attempt + 1}/{max_retries}): {e}")
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                logger.error(f"將在 {delay:.2f} 秒後重試...")
                time.sleep(delay)
        raise Exception(f"API 呼叫在 {max_retries} 次重試後仍然失敗。")

    def search_restaurants(self, location, radius=50000, limit=60, use_original_language=False,
                           place_types=['restaurant']):
        try:
            logger.info(f"正在搜尋 {location} 附近的地點...")

            logger.info("正在獲取地點座標...")
            geocode_result = self._make_api_call(self.gmaps.geocode, location)
            logger.info(f"API調用次數: {self.api_call_count}")

            if not geocode_result:
                logger.warning(f"無法找到地點: {location} 的座標。")
                return

            lat_lng = geocode_result[0]['geometry']['location']
            logger.info(f"找到座標: {lat_lng}")

            language_param = None if use_original_language else 'en'

            all_restaurants_raw = []

            for place_type in place_types:
                logger.info(f"\n  > 正在搜尋類型: {place_type}...")
                next_page_token = None
                page_num = 1
                while True:
                    logger.info(f"    > 正在獲取 {place_type} 第 {page_num} 頁的地點結果...")
                    places_result = self._make_api_call(
                        self.gmaps.places_nearby,
                        location=lat_lng,
                        radius=radius,
                        type=place_type,
                        language=language_param,
                        page_token=next_page_token
                    )
                    logger.info(f"API調用次數: {self.api_call_count}")

                    if not places_result:
                        logger.info(f"    > 沒有更多 {place_type} 附近地點結果。")
                        break

                    current_page_restaurants = places_result.get('results', [])
                    all_restaurants_raw.extend(current_page_restaurants)
                    logger.info(f"    > 當前頁面找到 {len(current_page_restaurants)} 家 {place_type}。")
                    logger.info(f"    > 目前已收集 {len(all_restaurants_raw)} 家地點 (含重複，所有類型)。")

                    next_page_token = places_result.get('next_page_token')

                    if not next_page_token:
                        logger.info(f"    > {place_type} 沒有下一頁結果。")
                        break
                    else:
                        logger.info(f"    > 發現 {place_type} 下一頁結果，等待片刻後繼續...")
                        time.sleep(2)
                    page_num += 1

            unique_ids_in_current_run = set()
            restaurants_to_process_final = []
            for restaurant in all_restaurants_raw:
                place_id = restaurant.get('place_id')
                if place_id and \
                        place_id not in self.processed_place_ids and \
                        place_id not in unique_ids_in_current_run:
                    restaurants_to_process_final.append(restaurant)
                    unique_ids_in_current_run.add(place_id)

            restaurants_to_process = restaurants_to_process_final[:limit]

            logger.info(f"\n從 {location} 去重後找到並將處理 {len(restaurants_to_process)} 家新地點詳細資訊...")
            if not restaurants_to_process:
                logger.info(f"此區域沒有新的地點需要處理。")
                return

            for i, restaurant in enumerate(restaurants_to_process, 1):
                place_id = restaurant.get('place_id')
                if not place_id:
                    logger.warning(f"警告: 地點 {restaurant.get('name', 'N/A')} 缺少 place_id，跳過詳細資訊獲取。")
                    continue

                logger.info(
                    f"  > [{i}/{len(restaurants_to_process)}] 正在處理新地點: {restaurant.get('name', 'N/A')} (ID: {place_id})...")
                restaurant_info = self.get_restaurant_details(restaurant, use_original_language)
                if restaurant_info:
                    restaurant_info['place_id'] = place_id
                    self.restaurants_data.append(restaurant_info)
                    self.processed_place_ids.add(place_id)
                    logger.info(f"  > 已獲取並儲存: {restaurant_info['name']}")
                else:
                    logger.warning(f"  > 無法獲取地點 {restaurant.get('name', 'N/A')} 的詳細資訊。")

                time.sleep(1)

        except Exception as e:
            logger.error(f"搜尋地點時發生錯誤: {e}")
            logger.error(f"目前API調用次數: {self.api_call_count}")

    def get_restaurant_details(self, restaurant, use_original_language=False):
        try:
            place_id = restaurant.get('place_id')
            if not place_id:
                logger.warning("警告: 地點缺少place_id，跳過獲取詳細資訊。")
                return None

            language_param = None if use_original_language else 'en'

            place_details = self._make_api_call(
                self.gmaps.place,
                place_id=place_id,
                fields=['name', 'rating', 'user_ratings_total', 'formatted_address', 'reviews', 'opening_hours'],
                language=language_param
            )

            if not place_details or 'result' not in place_details:
                logger.warning(f"無法從 Place Details API 獲取 {place_id} 的結果。")
                return None

            result = place_details['result']

            restaurant_info = {
                'name': result.get('name', 'N/A'),
                'rating': result.get('rating', 'N/A'),
                'total_ratings': result.get('user_ratings_total', 'N/A'),
                'address': result.get('formatted_address', 'N/A'),
                'reviews': []
            }

            opening_hours_data = result.get('opening_hours')
            if opening_hours_data and 'weekday_text' in opening_hours_data:
                restaurant_info['opening_hours'] = json.dumps(opening_hours_data['weekday_text'], ensure_ascii=False)
            else:
                restaurant_info['opening_hours'] = 'N/A'

            reviews = result.get('reviews', [])
            for review in reviews:
                review_info = {
                    'author': review.get('author_name', 'N/A'),
                    'rating': review.get('rating', 'N/A'),
                    'text': review.get('text', 'N/A'),
                    'time': datetime.fromtimestamp(review.get('time', 0)).strftime('%Y-%m-%d %H:%M:%S'),
                    'language': review.get('language', 'unknown')
                }
                restaurant_info['reviews'].append(review_info)

            return restaurant_info

        except Exception as e:
            logger.error(f"獲取地點詳細資訊時發生錯誤: {e}")
            return None

    def save_to_csv(self, filename='restaurants_data.csv'):
        try:
            fieldnames = ['restaurant_name', 'rating', 'total_ratings', 'address', 'place_id', 'opening_hours',
                          'review_author', 'review_rating', 'review_text', 'review_time', 'review_language']

            with open(filename, 'w', newline='', encoding='utf-8-sig') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()

                for restaurant in self.restaurants_data:
                    restaurant_base = {
                        'restaurant_name': restaurant['name'],
                        'rating': restaurant['rating'],
                        'total_ratings': restaurant['total_ratings'],
                        'address': restaurant['address'],
                        'place_id': restaurant.get('place_id', ''),
                        'opening_hours': restaurant.get('opening_hours', 'N/A')
                    }

                    if restaurant['reviews']:
                        for review in restaurant['reviews']:
                            writer.writerow({
                                **restaurant_base,
                                'review_author': review['author'],
                                'review_rating': review['rating'],
                                'review_text': review['text'],
                                'review_time': review['time'],
                                'review_language': review.get('language', 'unknown')
                            })
                    else:
                        writer.writerow({
                            **restaurant_base,
                            'review_author': '',
                            'review_rating': '',
                            'review_text': '',
                            'review_time': '',
                            'review_language': ''
                        })

            logger.info(f"資料已保存至 {filename}")
            logger.info(f"共獲取 {len(self.restaurants_data)} 家地點資料")
            logger.info(f"實際保存的獨特地點數量: {len(self.processed_place_ids)}")

        except Exception as e:
            logger.error(f"保存CSV時發生錯誤: {e}")

    def print_summary(self):
        # 這個方法仍然使用 print，因為它通常是程式結束時的最終摘要，
        # 並且您可能希望它以標準輸出方式呈現。
        # 如果您希望它也進入日誌檔案，可以將 print 替換為 logger.info
        print("\n" + "=" * 60)
        print("🎉 網格搜尋完成！搜尋結果摘要")
        print("=" * 60)
        print(f"🏪 總共找到 {len(self.restaurants_data)} 家地點 (包括重複的詳細資訊條目)")
        print(f"🔑 獨特地點數量: {len(self.processed_place_ids)} 家")
        print(f"📞 API調用次數: {self.api_call_count}")
        print(f"💰 實際費用: ${self.api_call_count * 0.017:.2f} USD")

        total_reviews = sum(len(restaurant['reviews']) for restaurant in self.restaurants_data)
        print(f"💬 總評論數: {total_reviews}")

        if len(self.restaurants_data) > 0:
            avg_reviews_per_restaurant = total_reviews / len(self.restaurants_data)
            print(f"📊 平均每家地點評論數: {avg_reviews_per_restaurant:.1f}")

        ratings = [r['rating'] for r in self.restaurants_data if isinstance(r['rating'], (int, float))]
        if ratings:
            avg_rating = sum(ratings) / len(ratings)
            print(f"⭐ 平均評分: {avg_rating:.1f}/5.0")

        print("=" * 60)


def get_location_config():
    return [
        {
            "name": "Birmingham City Centre, Birmingham, UK",
            "radius": 1000,
            "limit": 60,
            "description": "伯明翰市中心核心區"
        },
        {
            "name": "Birmingham Jewellery Quarter, Birmingham, UK",
            "radius": 800,
            "limit": 60,
            "description": "珠寶區"
        },
        {
            "name": "Birmingham Chinatown, Birmingham, UK",
            "radius": 600,
            "limit": 60,
            "description": "中國城區域"
        },
        {
            "name": "Brindleyplace, Birmingham, UK",
            "radius": 800,
            "limit": 60,
            "description": "布林德利廣場"
        },
        {
            "name": "Digbeth, Birmingham, UK",
            "radius": 800,
            "limit": 60,
            "description": "迪格貝斯區"
        },
        {
            "name": "Birmingham Mailbox, Birmingham, UK",
            "radius": 600,
            "limit": 60,
            "description": "郵箱購物中心區域"
        },
        {
            "name": "Birmingham New Street Station, Birmingham, UK",
            "radius": 500,
            "limit": 60,
            "description": "新街車站區域"
        },
        {
            "name": "Bull Ring, Birmingham, UK",
            "radius": 500,
            "limit": 60,
            "description": "牛環購物中心"
        },

        {
            "name": "University of Birmingham, Birmingham, UK",
            "radius": 2000,
            "limit": 60,
            "description": "伯明翰大學主校區"
        },
        {
            "name": "Selly Oak, Birmingham, UK",
            "radius": 1500,
            "limit": 60,
            "description": "塞利橡樹區（學生區）"
        },
        {
            "name": "Edgbaston, Birmingham, UK",
            "radius": 1200,
            "limit": 60,
            "description": "埃德巴斯頓區"
        }
    ]
