from app.main import app
from app.field_api import router as field_router

# Keep the existing application intact while exposing the dedicated field API.
app.include_router(field_router)
