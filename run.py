import sys
from datetime import datetime
import os

# 從 scraper 套件中導入核心邏輯
from scraper.core import RestaurantScraper, get_location_config


def run_scraper_main():
    API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")  # Load from environment variable

    history_data_filename = "birmingham_restaurants_history.csv"
    current_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"birmingham_restaurants_{current_timestamp}.csv"

    scraper = RestaurantScraper(API_KEY, existing_csv_filename=history_data_filename)

    locations = get_location_config()

    # --- 新增: 定義要搜尋的地點類型列表 ---
    search_types = ["restaurant", "cafe", "bar", "pub", "takeaway", "fast_food"]  # 您可以根據需要調整這些類型
    # ------------------------------------

    print("=== 搜尋範圍設定 ===")
    print("🎯 使用網格搜尋法突破 60 家餐廳限制")
    print(f"🔍 將搜尋以下類型: {', '.join(search_types)}")  # 顯示搜尋類型
    print("📍 Birmingham City Centre 分為多個重疊區域:")
    city_centre_areas = [loc for loc in locations if
                         "Birmingham" in loc['name'] and "University" not in loc['name'] and "Selly Oak" not in loc[
                             'name'] and "Edgbaston" not in loc['name']]
    for i, location in enumerate(city_centre_areas, 1):
        print(f"   {i}. {location['description']} - {location['radius'] / 1000}km 半徑")

    print("\n📍 University of Birmingham 及周邊區域:")
    uob_areas = [loc for loc in locations if
                 "University" in loc['name'] or "Selly Oak" in loc['name'] or "Edgbaston" in loc['name']]
    for i, location in enumerate(uob_areas, 1):
        print(f"   {i}. {location['description']} - {location['radius'] / 1000}km 半徑")

    print(f"\n💡 總共 {len(locations)} 個搜尋區域，預計可獲取大量獨特地點")  # 更新描述
    print("🔄 自動去重功能將移除重複的地點，節省API費用")  # 更新描述
    print()

    print("\n=== 語言設定 ===")
    language_choice = input("選擇評論語言:\n1. 原文評論 (不翻譯)\n2. 英文翻譯\n請選擇 (1/2): ")
    use_original_language = (language_choice == '1')

    if use_original_language:
        print("將獲取原文評論")
    else:
        print("將獲取英文翻譯評論")

    num_locations = len(locations)
    # --- 更新 API 預估: 每個地點會對每個類型進行 Places Nearby Search ---
    num_search_types = len(search_types)
    total_max_restaurants_per_search = sum(loc['limit'] for loc in locations)  # 這裡的 limit 仍是單一地點的總獨特上限

    estimated_geocode_calls = num_locations
    estimated_nearby_search_calls = num_locations * num_search_types * 3  # 每個地點 * 每個類型 * 最多 3 頁

    # Place Details 的呼叫次數取決於去重後的實際數量，理論最大值是所有地點的 limit 總和。
    # 現實預估可以基於總地點數和每個地點預計貢獻的獨特地點數。
    estimated_place_details_calls_max = total_max_restaurants_per_search  # 理論最大值 (所有地點都返回滿60家且完全不重複)
    estimated_place_details_calls_realistic = int(num_locations * 30 * (num_search_types / 2))  # 粗略估計，可能更多獨特地點

    total_estimated_calls_worst_case = estimated_geocode_calls + estimated_nearby_search_calls + estimated_place_details_calls_max
    total_estimated_calls_realistic = estimated_geocode_calls + estimated_nearby_search_calls + estimated_place_details_calls_realistic

    print("=== API使用說明 ===")
    print("⚠️  Google Places API 限制:")
    print("    - 每個 Places Nearby Search (單一類型) 最多返回 60 家地點 (分 3 頁，每頁 20 家)")
    print("    - 最大搜尋半徑: 50公里")
    print(f"\n📊 預估API調用 (共 {num_locations} 個搜尋區域，{num_search_types} 種地點類型):")
    print(f"- Geocoding API: {estimated_geocode_calls} 次")
    print(f"- Places Nearby Search: 最多 {estimated_nearby_search_calls} 次 (每個地點 * 每個類型 * 最多 3 次，包括分頁)")
    print(f"- Place Details: 預估 {estimated_place_details_calls_realistic} 次 (去重後)")
    print(f"  └─ 理論最大值: {estimated_place_details_calls_max} 次 (無重複情況)")
    print(f"\n💰 預估費用 (基於 $0.017/次 Nearby Search 或 Place Details):")
    print(f"- 現實預估: ${total_estimated_calls_realistic * 0.017:.2f} USD")
    print(f"- 最壞情況: ${total_estimated_calls_worst_case * 0.017:.2f} USD")
    print(f"\n📝 注意:")
    print(f"- 使用網格搜尋法，預計可獲取大量獨特地點")
    print(f"- 重疊區域和不同類型的重複地點會自動去重，有效節省API費用")
    print(f"- 從 '{history_data_filename}' 加載歷史數據進行跨運行去重")

    confirm = input("\n是否繼續執行? (y/n): ")
    if confirm.lower() != 'y':
        print("程式已取消")
        return

    print("\n開始網格搜尋地點...")  # 更新描述
    print("=" * 50)

    for i, location_config in enumerate(locations, 1):
        print(f"\n🔍 [{i}/{len(locations)}] 搜尋區域: {location_config['description']}")
        print(f"📍 地點: {location_config['name']}")
        print(f"📏 半徑: {location_config['radius'] / 1000}km")

        # --- 新增 try-except 塊來捕獲 search_restaurants 呼叫時可能發生的錯誤 ---
        try:
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

            print(f"✅ 此區域新增 {new_restaurants_added_in_this_area} 家地點")
            print(f"📊 目前總計: {after_count} 家獨特地點")
            print("-" * 30)
        except Exception as e:
            print(f"❌ 錯誤: 在處理區域 '{location_config['description']}' 時發生問題: {e}")
            print("請檢查 API Key、網路連線或該區域的設定。程式將嘗試繼續處理下一個區域。")
            # 這裡選擇 `continue`，讓程式即使遇到錯誤也能嘗試處理其他區域
            continue
            # --------------------------------------------------------------------

    scraper.print_summary()
    scraper.save_to_csv(output_filename)

    print(f"\n🎯 網格搜尋策略成功完成！")
    print(f"📁 資料已保存至: {output_filename}")
    print(f"💡 提示: 將 '{output_filename}' 重命名為 '{history_data_filename}' 以供下次去重使用")

    print(f"\n🏆 最終統計")
    print(f"📞 實際API調用次數: {scraper.api_call_count}")
    print(f"💰 實際費用: ${scraper.api_call_count * 0.017:.2f} USD")
    print(f"🏪 獲取地點總數 (包含重複條目): {len(scraper.restaurants_data)} 家")  # 更新描述
    print(f"🔑 獨特地點總數: {len(scraper.processed_place_ids)} 家")  # 更新描述
    print(f"🎯 覆蓋Birmingham全區域: ✅")

    print(f"\n📈 搜尋效果分析:")
    print(f"- 預期最大地點數 (所有搜尋區域的上限總和): {total_max_restaurants_per_search} 家")  # 更新描述
    print(f"- 實際獲取獨特地點數: {len(scraper.processed_place_ids)} 家")  # 更新描述
    efficiency = (
                             len(scraper.processed_place_ids) / total_max_restaurants_per_search) * 100 if total_max_restaurants_per_search > 0 else 0
    print(f"- 搜尋效率 (獨特地點佔理論最大值): {efficiency:.1f}%")  # 更新描述
    if efficiency < 50:
        print("💡 效率較低可能是因為區域重疊導致大量重複，這是正常現象，去重功能已節省費用。")
    else:
        print("🎉 高效率搜尋，成功獲取大量獨特地點！")


if __name__ == "__main__":
    run_scraper_main()
