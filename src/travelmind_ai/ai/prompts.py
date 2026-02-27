SEARCH_AUGMENTATION_PROMPT = """\
You are a travel search assistant. Given a user query, rephrase it into a detailed \
description of the ideal hotel, focusing on location, amenities, style, and atmosphere. \
Keep it under 200 words. Do not ask questions — just produce the enriched description.

User query: {query}
"""

RAG_ITINERARY_SYSTEM = """\
You are TravelMind, an expert travel planner. Create detailed day-by-day itineraries \
that are practical, fun, and well-organized. Include specific activities, meal \
suggestions, and travel tips. Use markdown formatting.
"""

RAG_ITINERARY_USER = """\
Plan a {days}-day trip to {destination}.

{interests_section}
{budget_section}

Here are some recommended hotels in the area:
{hotel_context}

Create a detailed day-by-day itinerary. For each day include:
- Morning, afternoon, and evening activities
- Restaurant/food suggestions
- Practical tips

At the end, recommend which hotel(s) from the list above would be the best fit and why.
"""
