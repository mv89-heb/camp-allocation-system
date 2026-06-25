import pandas as pd

def sort_rooms(df):
    if "actual_capacity" in df.columns:
        return df.sort_values(by="actual_capacity", ascending=False)
    return df

def assign_groups(rooms_df, groups):
    assignments = []
    working_df = rooms_df.copy()

    for group in groups:
        size = group.get("size", 0)
        name = group.get("name", "Unknown")

        for index, room in working_df.iterrows():
            if room.get("actual_capacity", 0) >= size:
                assignments.append({
                    "room": room["room"],
                    "group": name,
                    "campers": size
                })
                working_df.at[index, "actual_capacity"] -= size
                break

    return assignments
