import os
import re

directory = r'c:\Users\smaul\Downloads\SW-AI\fraud_service'
banking_pattern = r"fetch\(['\"]http://localhost:5000([^'\"]*)['\"]\)"
fraud_pattern = r"fetch\(['\"]http://localhost:5001([^'\"]*)['\"]\)"

for root, dirs, files in os.walk(directory):
    for file in files:
        if file.endswith('.html'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check if dynamic host variable is already defined
            has_dynamic_host = 'const bankingBaseUrl' in content or 'const fraudBaseUrl' in content
            
            new_content = content
            
            # Replace localhost:5000 calls
            if 'http://localhost:5000' in content:
                print(f"Updating banking links in {file}")
                # Add the variable at the start of script blocks if not present
                # Or just do an inline replacement if we want to be quick
                new_content = re.sub(
                    r"fetch\(['\"]http://localhost:5000([^'\"]*)['\"]\)",
                    r"fetch(`${window.location.protocol}//${window.location.hostname}:5000\1`)",
                    new_content
                )

            # Replace localhost:5001 calls
            if 'http://localhost:5001' in content:
                print(f"Updating fraud links in {file}")
                new_content = re.sub(
                    r"fetch\(['\"]http://localhost:5001([^'\"]*)['\"]\)",
                    r"fetch(`${window.location.protocol}//${window.location.hostname}:5001\1`)",
                    new_content
                )
            
            if new_content != content:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)

print("Done updating URLs.")
