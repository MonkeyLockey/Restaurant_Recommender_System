import sys
from datetime import datetime
import os
import logging  # 新增導入

# 從 scraper 套件中導入核心邏輯
from scraper.core import RestaurantScraper, get_location_config


def run_scraper_main():
    API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")  # Load from environment variable

    history_data_filename = "birmingham_restaurants_history.csv"
    current_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"birmingham_restaurants_{current_timestamp}.csv"
    log_filename = f"birmingham_scraper_log_{current_timestamp}.txt"  # 新增: 日誌檔案名

    # --- 配置日誌系統 ---
    # 創建一個 logger 物件
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)  # 設定最低日誌級別為 INFO

    # 創建一個檔案處理器，用於寫入日誌檔案
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setLevel(logging.INFO)  # 檔案處理器也設定為 INFO 級別

    # 創建一個控制台處理器，用於輸出到控制台
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)  # 控制台處理器也設定為 INFO 級別

    # 定義日誌格式
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # 將處理器添加到 logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # 替換內建的 print 函式，讓所有 print 輸出也通過 logger.info
    # 注意: 這會影響所有 print 語句，包括第三方庫的 print
    # 但對於您的程式碼，我們將直接使用 logger.info
    # sys.stdout = file_handler.stream # 不推薦直接替換 sys.stdout，因為會影響 input()

    # --------------------

    # 創建爬蟲實例
    scraper = RestaurantScraper(API_KEY, existing_csv_filename=history_data_filename)

    locations = get_location_config()

    logger.info("=== 搜尋範圍設定 ===")
    logger.info("🎯 使用網格搜尋法突破 60 家地點限制")

    search_types = ["restaurant", "cafe", "bar", "pub", "takeaway", "fast_food"]
    logger.info(f"🔍 將搜尋以下類型: {', '.join(search_types)}")

    logger.info("📍 Birmingham City Centre 分為多個重疊區域:")
    city_centre_areas = [loc for loc in locations if
                         "Birmingham" in loc['name'] and "University" not in loc['name'] and "Selly Oak" not in loc[
                             'name'] and "Edgbaston" not in loc['name']]
    for i, location in enumerate(city_centre_areas, 1):
        logger.info(f"   {i}. {location['description']} - {location['radius'] / 1000}km 半徑")

    logger.info("\n📍 University of Birmingham 及周邊區域:")
    uob_areas = [loc for loc in locations if
                 "University" in loc['name'] or "Selly Oak" in loc['name'] or "Edgbaston" in loc['name']]
    for i, location in enumerate(uob_areas, 1):
        logger.info(f"   {i}. {location['description']} - {location['radius'] / 1000}km 半徑")

    logger.info(f"\n💡 總共 {len(locations)} 個搜尋區域，預計可獲取大量獨特地點")
    logger.info("🔄 自動去重功能將移除重複的地點，節省API費用")
    logger.info("")  # 為了日誌排版

    logger.info("\n=== 語言設定 ===")
    # input() 函式無法被 logging 模組捕獲，所以這裡仍然使用 input()
    language_choice = input("選擇評論語言:\n1. 原文評論 (不翻譯)\n2. 英文翻譯\n請選擇 (1/2): ")
    use_original_language = (language_choice == '1')

    if use_original_language:
        logger.info("將獲取原文評論")
    else:
        logger.info("將獲取英文翻譯評論")

    num_locations = len(locations)
    num_search_types = len(search_types)
    total_max_restaurants_per_search = sum(loc['limit'] for loc in locations)

    estimated_geocode_calls = num_locations
    estimated_nearby_search_calls = num_locations * num_search_types * 3

    estimated_place_details_calls_max = total_max_restaurants_per_search
    estimated_place_details_calls_realistic = int(num_locations * 30 * (num_search_types / 2))

    total_estimated_calls_worst_case = estimated_geocode_calls + estimated_nearby_search_calls + estimated_place_details_calls_max
    total_estimated_calls_realistic = estimated_geocode_calls + estimated_nearby_search_calls + estimated_place_details_calls_realistic

    logger.info("=== API使用說明 ===")
    logger.info("⚠️  Google Places API 限制:")
    logger.info("    - 每個 Places Nearby Search (單一類型) 最多返回 60 家地點 (分 3 頁，每頁 20 家)")
    logger.info("    - 最大搜尋半徑: 50公里")
    logger.info(f"\n📊 預估API調用 (共 {num_locations} 個搜尋區域，{num_search_types} 種地點類型):")
    logger.info(f"- Geocoding API: {estimated_geocode_calls} 次")
    logger.info(
        f"- Places Nearby Search: 最多 {estimated_nearby_search_calls} 次 (每個地點 * 每個類型 * 最多 3 次，包括分頁)")
    logger.info(f"- Place Details: 預估 {estimated_place_details_calls_realistic} 次 (去重後)")
    logger.info(f"  └─ 理論最大值: {estimated_place_details_calls_max} 次 (無重複情況)")
    logger.info(f"\n💰 預估費用 (基於 $0.017/次 Nearby Search 或 Place Details):")
    logger.info(f"- 現實預估: ${total_estimated_calls_realistic * 0.017:.2f} USD")
    logger.info(f"- 最壞情況: ${total_estimated_calls_worst_case * 0.017:.2f} USD")
    logger.info(f"\n📝 注意:")
    logger.info(f"- 使用網格搜尋法，預計可獲取大量獨特地點")
    logger.info(f"- 重疊區域和不同類型的重複地點會自動去重，有效節省API費用")
    logger.info(f"- 從 '{history_data_filename}' 加載歷史數據進行跨運行去重")

    confirm = input("\n是否繼續執行? (y/n): ")  # input() 仍然需要直接輸出到控制台
    if confirm.lower() != 'y':
        logger.info("程式已取消")
        return

    logger.info("\n開始網格搜尋地點...")
    logger.info("=" * 50)

    for i, location_config in enumerate(locations, 1):
        logger.info(f"\n🔍 [{i}/{len(locations)}] 搜尋區域: {location_config['description']}")
        logger.info(f"📍 地點: {location_config['name']}")
        logger.info(f"📏 半徑: {location_config['radius'] / 1000}km")

        before_count = len(scraper.processed_place_ids)
        scraper.search_restaurants(
            location=location_config['name'],
            radius=location_config['radius'],
            limit=location_config['limit'],
            use_original_language=use_original_language,
            place_types=search_types
        )
        after_count = len(scraper.processed_place_ids)
        new_restaurants_added_in_this_area = after_count - before_count

        logger.info(f"✅ 此區域新增 {new_restaurants_added_in_this_area} 家地點")
        logger.info(f"📊 目前總計: {after_count} 家獨特地點")
        logger.info("-" * 30)

    scraper.print_summary()  # 這個方法內部仍然使用 print，你可以選擇修改它或讓它保持原樣
    scraper.save_to_csv(output_filename)

    logger.info(f"\n🎯 網格搜尋策略成功完成！")
    logger.info(f"📁 資料已保存至: {output_filename}")
    logger.info(f"💡 提示: 將 '{output_filename}' 重命名為 '{history_data_filename}' 以供下次去重使用")

    logger.info(f"\n🏆 最終統計")
    logger.info(f"📞 實際API調用次數: {scraper.api_call_count}")
    logger.info(f"💰 實際費用: ${scraper.api_call_count * 0.017:.2f} USD")
    logger.info(f"🏪 獲取地點總數 (包含重複條目): {len(scraper.restaurants_data)} 家")
    logger.info(f"🔑 獨特地點總數: {len(scraper.processed_place_ids)} 家")
    logger.info(f"🎯 覆蓋Birmingham全區域: ✅")

    logger.info(f"\n📈 搜尋效果分析:")
    logger.info(f"- 預期最大地點數 (所有搜尋區域的上限總和): {total_max_restaurants_per_search} 家")
    logger.info(f"- 實際獲取獨特地點數: {len(scraper.processed_place_ids)} 家")
    efficiency = (
                             len(scraper.processed_place_ids) / total_max_restaurants_per_search) * 100 if total_max_restaurants_per_search > 0 else 0
    logger.info(f"- 搜尋效率 (獨特地點佔理論最大值): {efficiency:.1f}%")
    if efficiency < 50:
        logger.info("💡 效率較低可能是因為區域重疊導致大量重複，這是正常現象，去重功能已節省費用。")
    else:
        logger.info("🎉 高效率搜尋，成功獲取大量獨特地點！")


if __name__ == "__main__":
    run_scraper_main()
