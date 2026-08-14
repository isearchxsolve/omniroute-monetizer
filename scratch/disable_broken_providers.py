import sqlite3

db_path = r"C:\Users\Admin\.omniroute\storage.sqlite"

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Disable broken providers to prevent event loop hanging on boot
    cursor.execute("UPDATE provider_connections SET is_active = 0 WHERE name IN ('isearch.xsolve@gmail.com', 'niloydassana@gmail.com', 'Zed Manual Import (openai)') OR id IN ('179e4825-1e03-47de-accc-c6cb611a195c', 'e217f911-6909-4ec8-83d4-9558457f57c2', 'c8a7f56f-1753-483a-b593-5fdcf83b1dc2', 'a2eced8e-0b95-43e4-b71f-80ec92d68369', 'ad3b1ec6-3f17-4b7b-8388-0002e5c3d8b7', '3be84526-7924-4cec-bc95-eaec6bb8f604')")
    print(f"Disabled {cursor.rowcount} broken providers.")
    
    conn.commit()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
