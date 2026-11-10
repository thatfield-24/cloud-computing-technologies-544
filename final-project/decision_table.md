# Decision Table

| # | Decision | What I chose and why  |
| :--- | :--- | :--- |
| 1 | Applicaiton architecture | I chose a two-tier architecture consisting of an Advisor tier and a Weather Data tier. This separates application logic from weather data collection and allows each tier to scale independently. It also improves security by limiting the responsibilities and permissions of each tier. |
| 1a | Application Language | I chose Python for the application because it integrates well with AWS services through boto3 and provides useful libraries for API requests, input validation, and testing. Using Python also keeps the application and deployment code consistent. I also have more experience with Python than Node.js | 
| 2 | Weather data APIs | I will continue to use the National Weather Service API as the primary weather data source because it provides forecast informaiton for US locaitons. This ensures the applicaiton can provide as much accurate information as possible. | 
| 3 | Zip code lookup and coordinates | I will continue to use the zippopotam api to convert ZIP codes into coordinates. I will pair this with the zipcodes Python library to check for real US zip codes before the API call is ever made.|
| 4 | Morning and night decisions | I chose morning to be 12:00 AM to 11:59 AM  and Night to be 12:00 PM to 11:59 PM. |
| 5 | Weather data aggregation | I chose to use the average temperature, average wind speed, lowest visibility, peak UV index, and average humidity for each reporting period. These values provide a useful summary of the weather conditions throughout Morning and Night rather than relying on a single hourly measurement. |
| 6 | Heavy, mild, and no for rain/snow thresholds | I chose to use predefined thresholds in the application's Python code to categorize rain and snow as Heavy, Mild, or No. The categories will be calculated using precipitation probability and measured precipitation amounts. This ensures consistent results and prevents Gemini from making up weather classifications. The final numerical thresholds will be based on documented meteorological sources.|
| 7 | Data caching | I chose to use DynamoDB to cache weather facts and completed reports. Cached weather information will expire after one hour using DynamoDB TTL. This reduces repeated API requests, improves response times, and helps control application costs. | 
| 8 | 