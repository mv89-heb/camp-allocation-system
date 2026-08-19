from app.main import app
from app.field_api import router as field_router
from app.room_management import router as room_router

# Dedicated field API and manual room management.
app.include_router(field_router)
app.include_router(room_router)
