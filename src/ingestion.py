import csv
import json
import os
from typing import Generator

def load_csv_records(file_path: str) -> list[dict]:
    """Load records from a CSV file into a list of dictionaries with cleaned keys and values.

    Args:
        file_path (str): The path to the CSV file.

    Returns:
        list[dict]: A list of dictionaries representing the rows in the CSV.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    # 1. Verify that the file exists; if not, raise FileNotFoundError
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    # 2. Check if the file is empty (0 bytes)
    if os.path.getsize(file_path) == 0:
        return []

    records = []

    # 3. Open file using context management ('with') and explicit UTF-8 encoding
    with open(file_path, mode="r", encoding="utf-8") as file:
        # 4. Use built-in csv.DictReader to read rows
        reader = csv.DictReader(file)

        for row in reader:
            cleaned_row = {}
            for key, value in row.items():
                # Strip whitespace from keys
                cleaned_key = key.strip() if isinstance(key, str) else key

                # Strip whitespace from string values
                cleaned_value = value.strip() if isinstance(value, str) else value

                cleaned_row[cleaned_key] = cleaned_value

            records.append(cleaned_row)

    return records


def load_json_records(file_path: str) -> list[dict]:
    """Load records from a JSON file and validate that the root element is a list of dictionaries.

    Args:
        file_path (str): The path to the JSON file.

    Returns:
        list[dict]: A list of dictionaries representing records from the JSON file.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the JSON file contains invalid JSON or root object is not a list of dictionaries.
    """
    # 1. Verify that the file exists; if not, raise FileNotFoundError
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    # 2. Open and parse the JSON file
    try:
        with open(file_path, mode="r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as err:
        # 3. Handle invalid JSON with a clear, actionable error
        raise ValueError(f"Failed to parse JSON in file '{file_path}': {err.msg} (line {err.lineno}, column {err.colno})") from err

    # 4. Validate that the root is a list
    if not isinstance(data, list):
        raise ValueError(f"Expected a list of records in '{file_path}', but got '{type(data).__name__}'.")

    # Optional safety check: ensure each item in the list is actually a dictionary
    if any(not isinstance(item, dict) for item in data):
        raise ValueError(f"Expected all items in '{file_path}' to be dictionaries (records).")

    return data

def stream_csv_records(file_path: str) -> Generator[dict, None, None]:
    """Streams records from a CSV file one record at a time.
    Memory footprint remains O(1) regardless of file size.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    if os.path.getsize(file_path) == 0:
        return

    with open(file_path, mode="r", encoding="utf-8") as file:
        reader = csv.DictReader(file)

        for row in reader:
            cleaned_row = {}
            for key, value in row.items():
                # Filter out extra columns where DictReader assigns key as None
                if key is None:
                    continue

                cleaned_key = key.strip() if isinstance(key, str) else key
                cleaned_value = value.strip() if isinstance(value, str) else value
                cleaned_row[cleaned_key] = cleaned_value

            # Skip rows where all values are blank or empty strings
            if not any(val for val in cleaned_row.values()):
                continue

            yield cleaned_row
