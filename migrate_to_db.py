import pandas as pd
from app.database import engine, Base

print("🔄 מתחיל בהגירת הנתונים מ-CSV למסד הנתונים...")

# יצירת הטבלאות במסד הנתונים
Base.metadata.create_all(bind=engine)

try:
    req_df = pd.read_csv("data/inventory.csv")
    req_df.to_sql("requirements", engine, if_exists="replace", index=False)
    print("✅ קובץ התקן הועבר לטבלת requirements בהצלחה!")
except Exception as e:
    print(f"⚠️ שגיאה בהעברת התקן: {e}")

try:
    act_df = pd.read_csv("data/actual_inventory.csv")
    act_df.to_sql("actuals", engine, if_exists="replace", index=False)
    print("✅ קובץ המצאי הועבר לטבלת actuals בהצלחה!")
except Exception as e:
    print(f"⚠️ שגיאה (או שאין קובץ מצאי): {e}")

print("🎉 ההגירה הסתיימה! המערכת עכשיו פועלת על Database אמיתי.")
