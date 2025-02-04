from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
from enum import Enum
import httpx
from typing import List, Dict, Optional
from pydantic import BaseModel, Field

# Define response model
class FlightDetails(BaseModel):
    destination: str
    time: str
    company: str
    fnumber: str
    comment: Optional[str] = None

class DateFlights(BaseModel):
    departures: List[FlightDetails] = Field(default_factory=list)
    arrivals: List[FlightDetails] = Field(default_factory=list)

# Define movement type enum
class MovementType(str, Enum):
    departures = "D"
    arrivals = "A"

app = FastAPI(title="Tunisia Flights API", description="API to fetch flight information for Tunisian airports.")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_dates():
    """Returns a list of yesterday, today, and tomorrow's dates in (day, month, year) format."""
    today = datetime.now()
    return [
        (today - timedelta(days=1)).strftime("%d"), (today - timedelta(days=1)).strftime("%m"), (today - timedelta(days=1)).strftime("%Y"),
        today.strftime("%d"), today.strftime("%m"), today.strftime("%Y"),
        (today + timedelta(days=1)).strftime("%d"), (today + timedelta(days=1)).strftime("%m"), (today + timedelta(days=1)).strftime("%Y"),
    ]

@app.get("/flights/djerba", response_model=Dict[str, DateFlights], summary="Get all flights for Djerba")
async def get_djerba_flights():
    """
    Fetches all flights (departures & arrivals) for yesterday, today, and tomorrow at Djerba Airport.
    """
    port = "djerba"
    movements = [MovementType.departures, MovementType.arrivals]
    dates = get_dates()
    flights_by_date: Dict[str, DateFlights] = {}
    api_errors = []

    async with httpx.AsyncClient(verify=False, timeout=10) as client:
        for i in range(0, len(dates), 3):  # Iterate over sets of (day, month, year)
            day, month, year = dates[i], dates[i + 1], dates[i + 2]
            current_date = f"{day}-{month}-{year}"
            
            # Initialize date entry if not exists
            if current_date not in flights_by_date:
                flights_by_date[current_date] = DateFlights()
            
            for movement in movements:
                url = (
                    f"https://www.oaca.nat.tn/vols/api/flight/filter"
                    f"?frmmvtCod={movement}"
                    f"&frmaeropVil=-1"
                    f"&frmnumVol="
                    f"&frmairport={port}"
                    f"&frmday={day}"
                    f"&frmmonth={month}"
                    f"&frmacty={year}"
                    f"&frmhour=0"
                )
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                    data = response.json()
                    
                    if not isinstance(data, list):
                        api_errors.append({
                            "date": current_date,
                            "movement": "departures" if movement == "D" else "arrivals",
                            "error": "Unexpected response format"
                        })
                        continue  # Skip to the next request
                    
                    flight_details = [
                        FlightDetails(
                            destination=item["direction"],
                            time=item["heure"],
                            company=item["compagnie"].strip(),
                            fnumber=item["numVol"],
                            comment=item["commentaire"]
                        ) for item in data
                    ]
                    
                    # Group flights by movement type
                    if movement == MovementType.departures:
                        flights_by_date[current_date].departures.extend(flight_details)
                    else:
                        flights_by_date[current_date].arrivals.extend(flight_details)
                
                except httpx.HTTPStatusError as e:
                    api_errors.append({
                        "date": current_date,
                        "movement": "departures" if movement == "D" else "arrivals",
                        "error": f"API error {e.response.status_code}: {e.response.text}"
                    })
                
                except httpx.RequestError as e:
                    api_errors.append({
                        "date": current_date,
                        "movement": "departures" if movement == "D" else "arrivals",
                        "error": f"Network error: {str(e)}"
                    })
                
                except Exception as e:
                    api_errors.append({
                        "date": current_date,
                        "movement": "departures" if movement == "D" else "arrivals",
                        "error": f"Unexpected error: {str(e)}"
                    })
    
    # If no flights found and there are errors, raise an HTTPException
    if not flights_by_date and api_errors:
        raise HTTPException(status_code=500, detail={
            "message": "Unable to fetch flights",
            "errors": api_errors
        })
    
    return flights_by_date

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
