import sys
from datetime import datetime
import os
import logging
from scraper.core import RestaurantScraper, get_location_config
from dotenv import load_dotenv

load_dotenv()

def run_scraper_main():
    # --- Generate a unified base filename with timestamp ---
    current_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_filename = f"birmingham_restaurants_scrape_{current_timestamp}" # Unified base filename

    output_csv_filename = f"{base_filename}.csv" # CSV output filename
    log_filename = f"{base_filename}.txt"       # Log file name (.txt extension)

    # --- Configure logging: Output logs to a separate file and simultaneously to the console ---
    # logging.basicConfig here configures the root logger.
    # All loggers obtained from core.py (and any other modules) will inherit this configuration initially.
    logging.basicConfig(
        level=logging.INFO, # Set to INFO, displays INFO, WARNING, ERROR level messages
        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename, mode='w', encoding='utf-8'), # Output to file, 'w' mode creates a new file each run
            logging.StreamHandler(sys.stdout) # Also output to console
        ]
    )
    # Get an instance of the logger for run.py itself (optional, but recommended)
    main_logger = logging.getLogger(__name__)

    # --- NEW: Set a higher logging level specifically for the 'scraper.core' module ---
    # This will reduce the verbosity from internal scraping details, showing mostly warnings/errors.
    # Use logging.WARNING to see warnings and errors.
    # Use logging.ERROR to see only errors.
    logging.getLogger('scraper.core').setLevel(logging.WARNING)
    # ----------------------------------------------------------------------------------

    main_logger.info(f"Starting scraper run at: {current_timestamp}")
    main_logger.info(f"Logs will be output to: {log_filename}")
    main_logger.info(f"Scraping results will be saved to: {output_csv_filename}")
    # --------------------------------------------------------

    # Get API KEY from .env
    API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not API_KEY:
        main_logger.error("Error: GOOGLE_MAPS_API_KEY environment variable not set. Please set it before running.")
        sys.exit(1)  # Exit if API key is not found

    history_data_filename = "birmingham_restaurants_history.csv"

    scraper = RestaurantScraper(API_KEY, existing_csv_filename=history_data_filename)

    locations = get_location_config()

    # --- Define the list of place types to search for ---
    search_types = ["restaurant", "cafe", "bar", "pub", "takeaway", "fast_food"]  # You can adjust these types as needed
    # ----------------------------------------------------

    main_logger.info("=== Search Scope Settings ===")
    main_logger.info("Using grid search strategy to overcome the 60-restaurant limit")
    main_logger.info(f"Will search for the following types: {', '.join(search_types)}")
    main_logger.info("Birmingham City Centre is divided into overlapping areas:")
    city_centre_areas = [loc for loc in locations if
                         "Birmingham" in loc['name'] and "University" not in loc['name'] and "Selly Oak" not in loc[
                             'name'] and "Edgbaston" not in loc['name']]
    for i, location in enumerate(city_centre_areas, 1):
        main_logger.info(f"   {i}. {location['description']} - {location['radius'] / 1000}km radius")

    main_logger.info("\nUniversity of Birmingham and surrounding areas:")
    uob_areas = [loc for loc in locations if
                 "University" in loc['name'] or "Selly Oak" in loc['name'] or "Edgbaston" in loc['name']]
    for i, location in enumerate(uob_areas, 1):
        main_logger.info(f"   {i}. {location['description']} - {location['radius'] / 1000}km radius")

    main_logger.info(f"\nThere are a total of {len(locations)} search areas. Expecting to fetch a large number of unique places.")
    main_logger.info("Automatic deduplication will remove duplicate places, saving API costs.")
    main_logger.info("")

    main_logger.info("\n=== Language Settings ===")
    language_choice = input("Select review language:\n1. Original review text (no translation)\n2. English translation\nPlease choose (1/2): ")
    use_original_language = (language_choice == '1')

    if use_original_language:
        main_logger.info("Will fetch original review text.")
    else:
        main_logger.info("Will fetch English translated reviews.")

    num_locations = len(locations)
    # --- Updated API estimation: Each location will perform Places Nearby Search for each type ---
    num_search_types = len(search_types)
    total_max_restaurants_per_search = sum(loc['limit'] for loc in locations)  # The limit here is still the total unique limit for a single location

    estimated_geocode_calls = num_locations
    estimated_nearby_search_calls = num_locations * num_search_types * 3  # Each location * each type * up to 3 pages

    # The number of Place Details calls depends on the actual number after deduplication, the theoretical maximum is the sum of limits for all locations.
    # A realistic estimate can be based on the total number of locations and the estimated number of unique places each location contributes.
    estimated_place_details_calls_max = total_max_restaurants_per_search  # Theoretical maximum (if all locations return full 60 places and are completely unique)
    estimated_place_details_calls_realistic = int(num_locations * 30 * (num_search_types / 2))  # Rough estimate, could be more unique places

    total_estimated_calls_worst_case = estimated_geocode_calls + estimated_nearby_search_calls + estimated_place_details_calls_max
    total_estimated_calls_realistic = estimated_geocode_calls + estimated_nearby_search_calls + estimated_place_details_calls_realistic

    main_logger.info("=== API Usage Information ===")
    main_logger.info("Google Places API Limits:")
    main_logger.info("    - Places Nearby Search (single type) returns a maximum of 60 places per call (3 pages, 20 places per page).")
    main_logger.info("    - Maximum search radius: 50 kilometers.")
    main_logger.info(f"\nEstimated API Calls (total {num_locations} search areas, {num_search_types} place types):")
    main_logger.info(f"- Geocoding API: {estimated_geocode_calls} calls.")
    main_logger.info(f"- Nearby Search: Up to {estimated_nearby_search_calls} calls (per area * per type * up to 3 times, including pagination).")
    main_logger.info(f"- Place Details: Estimated {estimated_place_details_calls_realistic} calls (after deduplication).")
    main_logger.info(f"  └─ Theoretical maximum: {estimated_place_details_calls_max} calls (no duplicates).")
    main_logger.info(f"\nEstimated Cost (based on $0.017 USD per Nearby Search or Place Details call):")
    main_logger.info(f"- Realistic Estimate: ${total_estimated_calls_realistic * 0.017:.2f} USD")
    main_logger.info(f"- Worst-Case Estimate: ${total_estimated_calls_worst_case * 0.017:.2f} USD")
    main_logger.info("\nNote:")
    main_logger.info("- Using a grid search strategy is expected to yield a large number of unique places.")
    main_logger.info("- Duplicates due to overlapping areas and different types will be automatically deduplicated, effectively saving API costs.")
    main_logger.info(f"- Historical data from '{history_data_filename}' is loaded for cross-run deduplication.")

    confirm = input("\nDo you want to continue execution? (y/n): ")
    if confirm.lower() != 'y':
        main_logger.info("Program cancelled by user.")
        return

    main_logger.info("\nStarting grid search for places...")
    main_logger.info("=" * 50)

    for i, location_config in enumerate(locations, 1):
        main_logger.info(f"\n[{i}/{len(locations)}] Searching area: {location_config['description']}")
        main_logger.info(f"Location: {location_config['name']}")
        main_logger.info(f"Radius: {location_config['radius'] / 1000}km")

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

            main_logger.info(f"Added {new_restaurants_added_in_this_area} new places in this area.")
            main_logger.info(f"Current total unique places: {after_count}.")
            main_logger.info("-" * 30)
        except Exception as e:
            main_logger.error(f"Error: Problem occurred while processing area '{location_config['description']}': {e}")
            main_logger.error("Please check your API key, network connection, or configuration for this area. The program will attempt to continue with the next area.")
            continue

    scraper.print_summary()
    scraper.save_to_csv(output_csv_filename) # Use the new unified filename

    main_logger.info(f"\nGrid search strategy completed successfully!")
    main_logger.info(f"Data saved to: {output_csv_filename}")
    main_logger.info(f"Hint: Rename '{output_csv_filename}' to '{history_data_filename}' for deduplication in the next run.")

    main_logger.info(f"\nFinal Statistics")
    main_logger.info(f"Actual API calls: {scraper.api_call_count}")
    main_logger.info(f"Actual cost: ${scraper.api_call_count * 0.017:.2f} USD")
    main_logger.info(f"Total places fetched (including duplicate entries): {len(scraper.restaurants_data)} ")
    main_logger.info(f"Total unique places: {len(scraper.processed_place_ids)} ")
    main_logger.info(f"Birmingham overall coverage: ") # This line might need more context if it's meant to display a specific metric.

    main_logger.info(f"\nSearch Effectiveness Analysis:")
    main_logger.info(f"- Expected maximum number of places (sum of limits for all search areas): {total_max_restaurants_per_search} ")
    main_logger.info(f"- Actual unique places fetched: {len(scraper.processed_place_ids)} ")
    efficiency = (
                             len(scraper.processed_place_ids) / total_max_restaurants_per_search) * 100 if total_max_restaurants_per_search > 0 else 0
    main_logger.info(f"- Search efficiency (unique places as a percentage of theoretical maximum): {efficiency:.1f}%")
    if efficiency < 50:
        main_logger.info("Lower efficiency might be due to significant overlaps between areas, which is normal. Deduplication has saved costs.")
    else:
        main_logger.info("High efficiency search, successfully retrieved a large number of unique places!")


if __name__ == "__main__":
    run_scraper_main()