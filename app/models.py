from pydantic import BaseModel

class ActualInventoryUpdate(BaseModel):
    apartment: str
    beds: int = 0
    mattresses: int = 0
    closets: int = 0
    ac_units: int = 0
    ac_remotes: int = 0
    
