// Function to fetch nearby restaurants (now globally accessible)
window.fetchNearbyRestaurants = function(lat, lng, radius = 1000) {
    const url = `/get_nearby_restaurants?lat=${lat}&lng=${lng}&radius=${radius}`;
    console.log(`Nearby: Requesting nearby restaurant data: ${url}`);
    fetch(url)
        .then(response => {
            console.log(`Nearby: Received /get_nearby_restaurants response, status: ${response.status}`);
            if (!response.ok) {
                return response.json().then(errorData => {
                    throw new Error(errorData.error || `HTTP error! status: ${response.status}`);
                }).catch(() => {
                    throw new Error(`HTTP error! status: ${response.status}`);
                });
            }
            return response.json();
        })
        .then(data => {
            const container = document.getElementById('top-nearby-list-container');
            if (!container) {
                console.error("Nearby: Could not find 'top-nearby-list-container' element.");
                return;
            }
            container.innerHTML = ''; // Clear loading message

            if (data.error) {
                console.error("Nearby: Backend returned error message:", data.error);
                container.innerHTML = `
                    <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative" role="alert">
                        <strong class="font-bold">Error:</strong>
                        <span class="block sm:inline">${data.error}</span>
                    </div>
                `;
            } else if (data.length > 0) {
                console.log(`Nearby: Successfully loaded ${data.length} nearby restaurants.`);
                data.forEach(r => {
                    const restaurantCard = document.createElement('div');
                    restaurantCard.className = "border-b border-gray-200 pb-3 mb-3 last:border-0 last:pb-0 last:mb-0";
                    const avgRatingFormatted = typeof r.avg_rating === 'number' ? r.avg_rating.toFixed(1) : 'N/A';

                    restaurantCard.innerHTML = `
                        <a href="https://www.google.com/maps/...?query_place_id=${r.place_id}&q=${encodeURIComponent(r.restaurant_name)}"
                            target="_blank" rel="noopener noreferrer">
                            <h3 class="text-lg font-semibold text-indigo-600 hover:underline">${r.restaurant_name}</h3>
                        </a>
                        <p class="text-sm text-gray-500 mt-1">${r.address}</p>
                        <p class="text-sm text-gray-900 font-bold mt-1">
                            ⭐ ${avgRatingFormatted} <span class="text-gray-500 font-normal">(${r.total_ratings})</span>
                        </p>
                        <p class="text-xs text-gray-400 mt-1">📏 Approx. ${Math.round(r.distance_m)} meters away</p>
                    `;
                    container.appendChild(restaurantCard);
                });
            } else {
                console.log("Nearby: No top-rated nearby restaurants found.");
                container.innerHTML = `
                    <div class="text-center text-gray-500 py-4">
                        <p>No top-rated restaurants found nearby. Try entering a location or broadening your search radius.</p>
                    </div>
                `;
            }
        })
        .catch(error => {
            console.error('Nearby: Error loading nearby restaurants:', error);
            const container = document.getElementById('top-nearby-list-container');
            if (container) {
                container.innerHTML = `
                    <div class="text-center text-red-500 py-4">
                        <p>Failed to load nearby restaurants. Error: ${error.message}. Please check the browser console for details.</p>
                    </div>
                `;
            } else {
                console.error("Nearby: Error display: Could not find 'top-nearby-list-container' element.");
            }
        });
};
